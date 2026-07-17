"""
Reconstruct — the deterministic reconstruction sweep loop (M0).

The §2 loop from EXECUTION.md: deterministic frontier traversal → (optional) LLM reasoning →
probes → convergence. M0 implements the deterministic layer; the LLM hook is optional.
Builds a multichain ArchitectureGraph from seed addresses.
"""
from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable

from ..domain.abi import (
    address_array_getters,
    address_getters,
    address_keyed_struct_getters,
    indexed_address_getters,
)
from ..domain.activity import participants_from_trace
from ..domain.classify import classify_bytecode, type_from_name
from ..domain.clones import collapse_clones
from ..domain.cooccurrence import rank_neighbors, strong_neighbors
from ..domain.deployers import is_common_deployer
from ..domain.factory_events import create_event_topics, created_addresses_from_logs
from ..domain.getters import getter_purpose, speculative_struct_getters
from ..domain.labels import is_known_external
from ..domain.membership import classify as classify_membership
from ..domain.membership import membership_score
from ..domain.models import (
    ArchitectureGraph,
    ContractNode,
    EdgeType,
    LogicalEntity,
    NodeType,
    ProxyKind,
    Role,
    SourceTier,
    is_zero,
    node_key,
    norm_addr,
)
from ..domain.multichain import detect_mirrors
from ..domain.proxies import (
    SLOT_1822,
    SLOT_1967_ADMIN,
    SLOT_1967_BEACON,
    SLOT_1967_IMPL,
    SLOT_ZOS,
    detect_proxy,
)
from ..domain.reads import decode_address_array, decode_address_strict
from ..domain.singleton import (
    SINGLETON_TOPICS,
    dominant_topic0,
    logical_entities_from_logs,
    referenced_addresses_from_logs,
)
from ..domain.tokens import finalize_token_roles, is_reserved_asset
from ..ports import RpcPort
from .probes import (
    enumerate_address_index,
    enumerate_lz_peers,
    is_admin_role,
    is_lz_oapp,
    read_addr,
    read_raw,
    reserve_components,
    role_holders,
    role_name,
)

_PROXY_SLOTS = (SLOT_1967_IMPL, SLOT_1967_ADMIN, SLOT_1967_BEACON, SLOT_1822, SLOT_ZOS)


def _authorities_of(node: ContractNode) -> set[str]:
    """Who controls the node: proxy admin + role holders."""
    out: set[str] = set()
    if node.admin:
        out.add(norm_addr(node.admin))
    for r in node.roles:
        if r.holder:
            out.add(norm_addr(r.holder))
    return {a for a in out if a}


def _node_signals(graph: ArchitectureGraph, k: str, n: ContractNode,
                  members: set[str], authorities: set[str], proj_deployers: set[str]) -> set[str]:
    """Node membership signals relative to the CURRENT set of members (for iteration)."""
    signals: set[str] = set()
    for e in graph.edges:
        # proxying INCLUDES the impl (inclusive — "better to over-include"); the reserved status
        # of an external asset's impl is decided separately in is_reserved_asset (wins in token_role)
        if e.dst == k and e.edge_type == EdgeType.IS_PROXY_FOR:
            signals.add("is_proxy_or_impl")
        if e.dst == k and e.edge_type == EdgeType.MIRRORS_DEPLOYMENT:
            signals.add("multichain_mirror")
        if e.src == k and e.edge_type == EdgeType.HOLDS_ROLE_OVER and e.dst in members:
            signals.add("role_holder")
        if e.dst == k and e.edge_type == EdgeType.DEPENDS_ON and e.src in members:
            # an asset-getter (reserve token/underlying) does NOT confer membership — it's an external asset
            if "getter:asset" in e.label:
                continue
            if "getter" in e.label:      # struct/generic getter-exposed component
                signals.add("exposed_getter")
            else:
                signals.add("explicit_reference")
        if e.src == k and e.edge_type == EdgeType.CALLS and e.dst in members:
            signals.add("cooccurrence")
        if (e.dst == k and e.edge_type == EdgeType.CREATED_BY
                and e.src in members and "factory" in e.label):
            signals.add("factory_instance")
    if authorities & _authorities_of(n):
        signals.add("shared_admin")
    if (n.deployer and not is_common_deployer(n.deployer)
            and norm_addr(n.deployer) in proj_deployers):
        signals.add("same_deployer")
    return signals


def finalize_membership(graph: ArchitectureGraph) -> None:
    """
    Post-pass: project membership. CONTROL DECIDES — project authorities (admin/owner/
    timelock/multisig/role-hub) + structural getter chains; asset-getters (reserve tokens)
    and known-external → external.

    ITERATED to a fixpoint: once a node is recognized as a member, it itself becomes a source
    of membership for the next level (Pool→Provider→ACLManager→…) and its role holders join
    the authorities. A single-level pass broke registry chains at the 2nd step.
    """
    members = {k for k, n in graph.nodes.items() if n.is_scope}
    # reserve assets (the pool custodies them) — external by code, excluded from the member fixpoint
    asset_ref = {k for k in graph.nodes if is_reserved_asset(graph, k)}

    def _authorities() -> set[str]:
        auth: set[str] = set()
        for mk in members:
            auth |= _authorities_of(graph.nodes[mk])
            mn = graph.nodes[mk]
            if mn.node_type in (NodeType.MULTISIG, NodeType.TIMELOCK):
                auth.add(mn.address)
        return auth

    def _proj_deployers() -> set[str]:
        return {
            norm_addr(graph.nodes[mk].deployer)
            for mk in members
            if graph.nodes[mk].deployer and not is_common_deployer(graph.nodes[mk].deployer)
        }

    # --- fixpoint: grow members while new ones keep being recognized ---
    changed = True
    while changed:
        changed = False
        authorities, proj_deployers = _authorities(), _proj_deployers()
        for k, n in graph.nodes.items():
            if k in members or is_known_external(n.address) or k in asset_ref:
                continue
            sig = _node_signals(graph, k, n, members, authorities, proj_deployers)
            if membership_score(sig) >= 0.55:   # MEMBER_THRESHOLD
                members.add(k)
                changed = True

    # --- final assignment of membership/score ---
    authorities, proj_deployers = _authorities(), _proj_deployers()
    for k, n in graph.nodes.items():
        if n.is_scope:
            n.membership, n.membership_score = "member", 1.0
            continue
        if is_known_external(n.address):
            n.membership, n.membership_score = "external", 0.0
            if "external: known infra" not in n.notes:
                n.notes.append("external: known infra")
            continue
        if k in asset_ref:
            n.membership, n.membership_score = "external", 0.0
            if "external: asset (reserve/underlying)" not in n.notes:
                n.notes.append("external: asset (reserve/underlying)")
            continue
        sig = _node_signals(graph, k, n, members, authorities, proj_deployers)
        n.membership_score = round(membership_score(sig), 3)
        n.membership = classify_membership(n.membership_score)


async def reconstruct(
    seeds: list[tuple[int, str]],
    rpc: RpcPort,
    *,
    max_nodes: int | None = None,     # None = NO LIMIT (growth is bounded by
                                         # clone-collapse + a thin external boundary, not a counter).
                                         # a number is an optional safety cap.
    clone_cap: int = 50,
    clone_min_group: int = 4,
    probe_chains: list[int] | None = None,
    source: object | None = None,     # SourceLadder/resolver: name+tier+abi (optional)
    activity: object | None = None,   # ActivityPort: deployer/last-active/co-occurrence (optional)
    deep_cooccur: int = 0,               # trace_transaction on N sample txs of the seeds (0=off)
    concurrency: int = 8,                # how many frontier nodes to process in parallel
    existing: ArchitectureGraph | None = None,  # merge mode: expand an existing graph
    on_event: Callable[[str, dict], None] | None = None,
) -> ArchitectureGraph:
    """
    seeds        — [(chain_id, address)]; all marked is_scope=member.
    probe_chains — chains to check for cross-chain mirrors (same-address + codehash).
    on_event     — optional callback for structural events (for web visualization/logging):
                   on_event(kind, data). kind: visit|node|edge|mirror|clones|done.
    """
    def emit(kind: str, **data: object) -> None:
        if on_event:
            on_event(kind, data)

    merge = existing is not None
    graph = existing if merge else ArchitectureGraph()
    mirrored: set[str] = set()   # addresses that already had a mirror probe
    peered: set[str] = set()     # addresses that already had an LZ-peer probe
    peer_stub_chains: set[int] = set()  # chains of remote peers (for stubs if unreachable)
    seed_keys = {node_key(c, a) for c, a in seeds}
    # frontier item: (chain, addr, is_scope)
    frontier: deque[tuple[int, str]] = deque()
    scope_of: dict[str, bool] = {}
    for c, a in seeds:
        na = norm_addr(a)
        frontier.append((c, na))
        scope_of[node_key(c, na)] = not merge   # in merge mode new addresses are candidates, not scope

    visited: set[str] = set(graph.nodes.keys()) if merge else set()
    # nodes we run the ABI-getter traversal on (seeds + getter-discovered → multi-level traversal)
    getter_expand: set[str] = {node_key(c, norm_addr(a)) for c, a in seeds}
    enumerated_deployers: set[str] = set()   # deployer-hub discovery: each deployer once

    sem = asyncio.Semaphore(concurrency)

    async def _process(chain: int, addr: str) -> None:
        k = node_key(chain, addr)
        is_scope = scope_of.get(k, False)
        emit("visit", key=k, chain=chain, addr=addr, is_scope=is_scope,
             frontier=len(frontier), nodes=len(graph.nodes))

        try:
            code = await rpc.get_code(chain, addr)
        except Exception as e:  # noqa: BLE001
            graph.warn(f"get_code failed {k}: {e}")
            return

        if not code or code == "0x":
            graph.add_node(ContractNode(
                address=addr, chain_id=chain, node_type=NodeType.EOA,
                source_tier=SourceTier.ABSENT, is_scope=is_scope,
                membership="member" if is_scope else "candidate",
                membership_score=1.0 if is_scope else 0.3,
            ))
            return

        try:
            ch = await rpc.codehash(chain, addr)
        except Exception:  # noqa: BLE001
            ch = None

        # proxy detect: prefetch known slots (in parallel), then pure detect_proxy
        async def _slot(s: str, chain: int = chain, addr: str = addr) -> tuple[str, str | None]:
            try:
                return s.lower(), await rpc.get_storage_at(chain, addr, s)
            except Exception:  # noqa: BLE001
                return s.lower(), None
        slots = dict(await asyncio.gather(*[_slot(s) for s in _PROXY_SLOTS]))
        proxy = detect_proxy(code, lambda s: slots.get(s.lower()))

        # node type: proxy → PROXY; otherwise classify by bytecode selectors
        if proxy.kind != ProxyKind.NONE:
            ntype, iface_tags = NodeType.PROXY, []
        else:
            ntype, iface_tags = classify_bytecode(code)

        node = ContractNode(
            address=addr, chain_id=chain,
            node_type=ntype,
            proxy_kind=proxy.kind,
            implementation=proxy.implementation, admin=proxy.admin, beacon=proxy.beacon,
            codehash=ch, is_scope=is_scope,
            membership="member" if is_scope else "candidate",
            membership_score=1.0 if is_scope else 0.0,
        )
        if iface_tags:
            node.notes.append("iface: " + ", ".join(iface_tags))
        graph.add_node(node)

        # --- role-hub authority: role holders from RoleGranted/Revoked (#6) ---
        # ACLManager/RoleRegistry governs the project not via owner() but via roles
        # (Aave POOL_ADMIN/EMERGENCY_ADMIN/…). The hub becomes a member via an exposed_getter reference.
        # ADMIN roles → project authorities (confer membership); operational roles
        # (FLASH_BORROWER/BRIDGE — external integrators) are NOT authority → just a counter note.
        if "access_control" in iface_tags:
            op_roles: dict[str, int] = {}
            for role_hex, holder in await role_holders(rpc, chain, addr):
                if is_zero(holder):
                    continue
                if is_admin_role(role_hex):
                    node.roles.append(Role(role_name(role_hex), holder, "RoleGranted log"))
                    graph.add_edge(node_key(chain, holder), k,
                                   EdgeType.HOLDS_ROLE_OVER, role_name(role_hex))
                    frontier.append((chain, holder))
                else:
                    op_roles[role_name(role_hex)] = op_roles.get(role_name(role_hex), 0) + 1
            for rn, cnt in op_roles.items():
                node.notes.append(f"op-role {rn} x{cnt}")

        # --- source resolution: name / tier / abi (ladder: etherscan→sourcify→blockscout→decompile) ---
        if source is not None:
            try:
                info = await source.resolve(chain, addr, code=code)
            except TypeError:
                info = await source.resolve(chain, addr)
            if info:
                node.name = info.name
                try:
                    node.source_tier = SourceTier(info.tier)
                except ValueError:
                    node.source_tier = SourceTier.VERIFIED
                node.abi_present = bool(info.abi)
                # refine type from the name if selectors yielded UNKNOWN
                if node.node_type == NodeType.UNKNOWN:
                    hint = type_from_name(info.name)
                    if hint:
                        node.node_type = hint
                        node.notes.append("type from name")
                # a name containing "factory" outranks bytecode (factories sometimes have ERC selectors)
                if info.name and "factory" in info.name.lower() and node.node_type != NodeType.FACTORY:
                    node.node_type = NodeType.FACTORY
                    node.notes.append("factory by name")
                emit("source", key=k, name=info.name, tier=info.tier)

                # a proxy's ABI is empty (getters live on the implementation), but storage is on
                # the proxy → for proxies we take the impl ABI but CALL getters on the proxy address (self).
                getter_abi = info.abi
                if node.proxy_kind == ProxyKind.DIAMOND and source is not None:
                    # Diamond (EIP-2535): union of facet ABIs; getters are called on the proxy
                    try:
                        facets = decode_address_array(
                            await rpc.call(chain, addr, "0x52ef6b2c"))  # facetAddresses()
                    except Exception:  # noqa: BLE001
                        facets = []
                    union: list = []
                    for f in facets[:20]:
                        if is_zero(f):
                            continue
                        graph.add_edge(k, node_key(chain, f), EdgeType.IS_PROXY_FOR, "diamond facet")
                        frontier.append((chain, f))
                        scope_of.setdefault(node_key(chain, f), is_scope)
                        try:
                            fi = await source.resolve(chain, f)
                        except Exception:  # noqa: BLE001
                            fi = None
                        if fi and getattr(fi, "abi", None):
                            union += fi.abi
                    if union:
                        getter_abi = union
                elif node.implementation and source is not None:
                    try:
                        impl_info = await source.resolve(chain, node.implementation)
                    except Exception:  # noqa: BLE001
                        impl_info = None
                    if impl_info and getattr(impl_info, "abi", None):
                        getter_abi = impl_info.abi
                        if impl_info.name and (not node.name or "Proxy" in (node.name or "")):
                            node.name = impl_info.name

                # GETTER EXPANSION by PURPOSE + SPECULATIVE probe (source-independent):
                # the contract exposes components via view getters (getPool()/ADDRESSES_PROVIDER()).
                #  • struct  → project component: crawl deeper + membership signal.
                #  • asset   → external token (reserve/underlying): a leaf, do NOT crawl (save budget).
                #  • generic → any other address from the ABI: follow it, membership only candidate.
                # Structural signatures are probed EVEN WITHOUT an ABI (a blind read probe — exploratory).
                # Do NOT traverse token/oracle leaves (they don't expose project components → precision).
                _leaf = node.node_type in (NodeType.TOKEN, NodeType.ORACLE)
                if (is_scope or k in getter_expand) and not _leaf:
                    def _add_getter(a: str, sig: str, purpose: str,
                                    chain: int = chain, k: str = k) -> None:
                        if not a or is_zero(a) or is_known_external(a):
                            return
                        gk = node_key(chain, a)
                        label = {"struct": "getter:struct", "asset": "getter:asset"}.get(
                            purpose, "getter")
                        graph.add_edge(k, gk, EdgeType.DEPENDS_ON, f"{label} {sig}")
                        frontier.append((chain, a))
                        scope_of.setdefault(gk, False)
                        if purpose != "asset":          # asset is an external leaf, don't go deeper
                            getter_expand.add(gk)

                    abi_sigs = address_getters(getter_abi)[:24] if getter_abi else []
                    # blind probe of structural getters: FULL when there's no ABI (bytecode-only is
                    # the only way to reveal the architecture); only a top-priority top-up when an ABI
                    # exists (there the real getters are already enumerated → save calls).
                    spec_all = speculative_struct_getters()
                    spec_src = spec_all if not getter_abi else spec_all[:12]
                    spec_sigs = [s for s in spec_src if s not in abi_sigs]
                    single_sigs = abi_sigs + spec_sigs
                    svals = await asyncio.gather(*[read_raw(rpc, chain, addr, s) for s in single_sigs])
                    for sig, val in zip(single_sigs, svals, strict=False):
                        a = decode_address_strict(val) if val else None
                        if a:
                            _add_getter(a, sig, getter_purpose(sig))
                    # address[] getters from the ABI (reserve lists → asset leaves + reserve set)
                    reserves: list[str] = []
                    if getter_abi:
                        asigs = address_array_getters(getter_abi)[:8]
                        avals = await asyncio.gather(*[read_raw(rpc, chain, addr, s) for s in asigs])
                        for sig, val in zip(asigs, avals, strict=False):
                            purpose = getter_purpose(sig)
                            arr = decode_address_array(val, cap=60) if val else []
                            if purpose == "asset":
                                reserves.extend(arr)   # reserve underlyings for reserve-keyed lookups
                            for a in arr:
                                _add_getter(a, sig, purpose)
                        # indexed getters `getX(uint i)` — registry by index (Liquity/pairs)
                        for name in indexed_address_getters(getter_abi)[:5]:
                            for a in await enumerate_address_index(rpc, chain, addr, name, cap=40):
                                _add_getter(a, f"{name}(i)", getter_purpose(f"{name}()"))

                        # RESERVE-KEYED struct expansion: getReserveData(asset)→struct with
                        # aToken/debt/strategy — Aave's OWN per-reserve contracts (where bugs live).
                        # Generalizes to Compound markets(addr), Euler, etc. Components → own.
                        if reserves:
                            for name in address_keyed_struct_getters(getter_abi)[:4]:
                                comps = await reserve_components(rpc, chain, addr, name, reserves)
                                for a in comps:
                                    if a not in reserves:   # not an underlying, but a project component
                                        _add_getter(a, f"{name}(reserve)", "struct")

                # logs discovery: instances/markets from Create* logs (no getter list).
                # Topic filter over curated Create topics → "hot" singletons (Morpho Blue,
                # millions of logs) answer only with creation events; a plain getLogs would hang.
                # Run on factories and on seeds (a singleton is a seed but not FACTORY by type).
                if node.node_type == NodeType.FACTORY or k in seed_keys:
                    try:
                        logs = await rpc.get_logs(
                            chain, addr, topics=[create_event_topics()], from_block=0)
                    except Exception:  # noqa: BLE001
                        logs = []
                    if logs and dominant_topic0(logs) in SINGLETON_TOPICS:
                        # singleton: markets = logical entities without an address; reusable
                        # components (IRM/tokens) = real nodes; per-market oracle → into refs.
                        for a in referenced_addresses_from_logs(logs, min_count=3, cap=20):
                            if not is_zero(a) and not is_known_external(a):
                                graph.add_edge(k, node_key(chain, a),
                                               EdgeType.DEPENDS_ON, "market component (event)")
                                frontier.append((chain, a))
                                scope_of.setdefault(node_key(chain, a), False)
                        for le in logical_entities_from_logs(logs, cap=60):
                            refs = [node_key(chain, x) for x in le["refs"] if not is_zero(x)]
                            graph.logical.append(LogicalEntity(
                                id=le["id"], kind="market", parent=k, refs=refs))
                        if graph.logical:
                            emit("logical", key=k, count=len(graph.logical))
                    else:
                        inst = created_addresses_from_logs(logs, cap=40)
                        for a in inst:
                            if not is_zero(a) and not is_known_external(a):
                                graph.add_edge(k, node_key(chain, a),
                                               EdgeType.CREATED_BY, "factory event")
                                frontier.append((chain, a))
                                scope_of.setdefault(node_key(chain, a), False)
                        if inst:
                            emit("factory", key=k, instances=len(inst))

        # --- activity: deployer + last-active + co-occurrence (for scope nodes) ---
        if activity is not None and is_scope:
            summ = await activity.summary(chain, addr)
            if summ:
                if summ.deployer and not is_zero(summ.deployer):
                    node.deployer = summ.deployer
                    graph.add_edge(node_key(chain, summ.deployer), k,
                                   EdgeType.CREATED_BY, "deployer")
                    # common deployers (Create2/Safe factories) aren't expanded as a project node
                    if not is_common_deployer(summ.deployer):
                        frontier.append((chain, summ.deployer))
                    # deployer-hub: what ELSE the project deployer deployed (factories/resolvers
                    # not structurally linked) — a bridge to them without an Etherscan key (Blockscout)
                    dk = node_key(chain, summ.deployer)
                    if (not is_common_deployer(summ.deployer) and dk not in enumerated_deployers
                            and hasattr(activity, "deployments_by")):
                        enumerated_deployers.add(dk)
                        try:
                            siblings = await activity.deployments_by(chain, summ.deployer, cap=30)
                        except Exception:  # noqa: BLE001
                            siblings = []
                        for s in siblings:
                            if not is_zero(s) and not is_known_external(s):
                                graph.add_edge(dk, node_key(chain, s),
                                               EdgeType.CREATED_BY, "sibling deploy")
                                frontier.append((chain, s))
                                scope_of.setdefault(node_key(chain, s), False)
                                getter_expand.add(node_key(chain, s))
                if summ.last_active_ts:
                    node.state["last_active"] = summ.last_active_ts
                if summ.tx_count is not None:
                    node.state["tx_count"] = str(summ.tx_count)
                if summ.top_callers:
                    node.state["top_callers"] = ",".join(a for a, _ in summ.top_callers[:5])
                if summ.sample_txs:
                    node.state["sample_txs"] = ",".join(summ.sample_txs[:5])
                # top-3 callers → frontier (candidates) + CALLS edge (co-occurrence lead)
                for caller, _cnt in summ.top_callers[:3]:
                    if caller and not is_zero(caller) and not is_common_deployer(caller):
                        graph.add_edge(node_key(chain, caller), k, EdgeType.CALLS, "top caller")
                        frontier.append((chain, caller))
                # deep co-occurrence: trace the seed's sample txs → full tree of participants
                if deep_cooccur and k in seed_keys and summ.sample_txs:
                    sets: list[list[str]] = []
                    for tx in summ.sample_txs[:deep_cooccur]:
                        try:
                            frames = await rpc.trace_transaction(chain, tx)
                        except Exception:  # noqa: BLE001
                            continue
                        sets.append(list(participants_from_trace(frames)))
                    ranked = rank_neighbors(sets, addr, top=15)
                    added = 0
                    for neigh in strong_neighbors(ranked, min_count=2, min_ratio=0.3):
                        if neigh and not is_zero(neigh) and not is_common_deployer(neigh) and added < 8:
                            graph.add_edge(node_key(chain, neigh), k, EdgeType.CALLS, "co-occurs (trace)")
                            frontier.append((chain, neigh))
                            added += 1
                    emit("cooccur", key=k, traced=len(sets), neighbors=added)

                emit("activity", key=k, deployer=summ.deployer,
                     last_active=summ.last_active_ts, callers=len(summ.top_callers))
        elif activity is not None and code and code != "0x" and not node.deployer:
            # non-scope contract: lightweight deployer lookup (for deployer closure)
            try:
                dep = await activity.deployer(chain, addr)
            except Exception:  # noqa: BLE001
                dep = None
            if dep and not is_zero(dep):
                node.deployer = dep
                graph.add_edge(node_key(chain, dep), k, EdgeType.CREATED_BY, "deployer")

        # --- expand proxy targets ---
        if proxy.implementation:
            graph.add_edge(k, node_key(chain, proxy.implementation),
                           EdgeType.IS_PROXY_FOR, "proxy -> impl")
            frontier.append((chain, proxy.implementation))
            scope_of[node_key(chain, proxy.implementation)] = is_scope  # impl = part of the project
        if proxy.admin and not is_zero(proxy.admin):
            node.roles.append(Role("proxyAdmin", proxy.admin, "1967-admin-slot"))
            graph.add_edge(node_key(chain, proxy.admin), k,
                           EdgeType.HOLDS_ROLE_OVER, "proxy admin")
            frontier.append((chain, proxy.admin))
        if proxy.beacon:
            graph.add_edge(k, node_key(chain, proxy.beacon), EdgeType.DEPENDS_ON, "beacon")
            frontier.append((chain, proxy.beacon))
            scope_of[node_key(chain, proxy.beacon)] = is_scope
            # resolve the real impl behind the beacon: beacon.implementation()
            beacon_impl = await read_addr(rpc, chain, proxy.beacon, "implementation()")
            if beacon_impl:
                node.implementation = beacon_impl
                graph.add_edge(k, node_key(chain, beacon_impl),
                               EdgeType.IS_PROXY_FOR, "proxy -> impl (via beacon)")
                frontier.append((chain, beacon_impl))
                scope_of[node_key(chain, beacon_impl)] = is_scope

        # --- roles: owner() ---
        owner = await read_addr(rpc, chain, addr, "owner()")
        if owner:
            node.roles.append(Role("owner", owner, "owner()"))
            graph.add_edge(node_key(chain, owner), k, EdgeType.HOLDS_ROLE_OVER, "owner")
            frontier.append((chain, owner))

        # --- deployer ---
        try:
            creation = await rpc.get_creation(chain, addr)
        except Exception:  # noqa: BLE001
            creation = None
        if creation and creation.deployer:
            node.deployer = norm_addr(creation.deployer)
            graph.add_edge(node_key(chain, node.deployer), k, EdgeType.CREATED_BY, "deployer")

        emit("node", key=k, type=node.node_type.value, proxy=proxy.kind.value,
             impl=node.implementation, admin=node.admin, is_scope=is_scope)

        # --- cross-chain mirrors (probe each address ONCE, directed edges) ---
        if is_scope and probe_chains and addr not in mirrored:
            mirrored.add(addr)

            async def _ch(pc: int, addr: str = addr) -> tuple[int, str | None]:
                try:
                    return pc, await rpc.codehash(pc, addr)
                except Exception:  # noqa: BLE001
                    return pc, None
            probe = [pc for pc in probe_chains if pc != chain]
            per = dict(await asyncio.gather(*[_ch(pc) for pc in probe]))
            mirrors = detect_mirrors(ch, per)
            for mc in mirrors:
                graph.add_edge(k, node_key(mc, addr),
                               EdgeType.MIRRORS_DEPLOYMENT, "same address, same codehash")
                frontier.append((mc, addr))
                scope_of[node_key(mc, addr)] = True
            if mirrors:
                emit("mirror", addr=addr, from_chain=chain, chains=mirrors)

        # --- cross-chain peers (#7): a LayerZero OApp/OFT knows its remote deployments via
        # peers(eid)/trustedRemote — DIFFERENT code and address, not a mirror. Link with PEER_OF. ---
        if is_scope and probe_chains and addr not in peered:
            peered.add(addr)
            if await is_lz_oapp(rpc, chain, addr):
                for rc, remote in await enumerate_lz_peers(rpc, chain, addr):
                    if is_zero(remote):
                        continue
                    graph.add_edge(k, node_key(rc, remote), EdgeType.PEER_OF, "lz peer")
                    frontier.append((rc, remote))
                    scope_of[node_key(rc, remote)] = True   # same project on another chain
                    peer_stub_chains.add(rc)

    # --- BFS in waves: process a frontier level concurrently (bounded by a semaphore) ---
    async def _bounded(c: int, a: str) -> None:
        async with sem:
            await _process(c, a)

    # NO LIMIT by default (max_nodes=None): take the whole frontier wave. Growth is bounded by
    # real disciplines (clone-collapse of foreign clones + a thin external boundary — we capture
    # an external node but don't recurse into its world), not by an artificial counter.
    while frontier and (max_nodes is None or len(graph.nodes) < max_nodes):
        wave: list[tuple[int, str]] = []
        room = (max_nodes - len(graph.nodes)) if max_nodes is not None else len(frontier)
        while frontier and len(wave) < room:
            c, a = frontier.popleft()
            key = node_key(c, a)
            if key in visited:
                continue
            visited.add(key)
            wave.append((c, a))
        if not wave:
            break
        await asyncio.gather(*[_bounded(c, a) for c, a in wave])

    # --- stub nodes for peers on unprobed chains: a PEER_OF edge must not dangle ---
    for e in graph.edges:
        if e.edge_type == EdgeType.PEER_OF and e.dst not in graph.nodes:
            pc, pa = e.dst.split(":", 1)
            stub = ContractNode(
                address=pa, chain_id=int(pc), node_type=NodeType.UNKNOWN,
                source_tier=SourceTier.ABSENT, is_scope=True,
                membership="member", membership_score=1.0,
            )
            stub.notes.append("cross-chain peer (chain not probed)")
            graph.add_node(stub)

    # --- collapse clones (by logical identity: factory/beacon/impl/codehash) ---
    factory_of = {
        e.dst.split(":", 1)[1]: e.src.split(":", 1)[1]
        for e in graph.edges
        if e.edge_type == EdgeType.CREATED_BY and "factory" in e.label and ":" in e.dst
    }
    kept, classes = collapse_clones(
        list(graph.nodes.values()), cap=clone_cap, min_group=clone_min_group,
        factory_of=factory_of,
    )
    graph.nodes = {n.key: n for n in kept}
    graph.clone_classes = classes
    if classes:
        emit("clones", count=len(classes),
             total=sum(c.total_count for c in classes))

    finalize_membership(graph)
    finalize_token_roles(graph)   # own | reserved | transient for token nodes

    if not merge:
        graph.roots = sorted(seed_keys)
    graph.meta.update({"visited": len(visited), "node_count": len(graph.nodes)})
    if max_nodes is not None and len(graph.nodes) >= max_nodes:
        graph.warn(f"max_nodes limit hit ({max_nodes}) — graph may be incomplete "
                   f"(the limit is optional; default None = no limit)")
    emit("done", chains=graph.chains, nodes=len(graph.nodes),
         edges=len(graph.edges), clone_classes=len(graph.clone_classes))
    return graph
