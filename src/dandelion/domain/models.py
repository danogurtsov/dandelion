"""
OAR data model — On-chain Architecture Reconstruction.

The project graph reconstructed FROM on-chain data (addresses + state + links),
not from a GitHub repository. Everything is JSON-serializable — a machine-readable
map of the protocol to build on-chain research on.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum

# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #

class SourceTier(StrEnum):
    """How "readable" a contract is — affects the achievable level of proof."""
    VERIFIED = "verified"          # verified source + ABI
    PARTIAL = "partial"            # partial / ABI only
    DECOMPILED = "decompiled"      # recovered by a decompiler
    BYTECODE_ONLY = "bytecode"     # bytecode / selectors only
    ABSENT = "absent"              # EOA or empty


class NodeType(StrEnum):
    PROXY = "proxy"
    IMPLEMENTATION = "implementation"
    TOKEN = "token"
    POOL = "pool"
    VAULT = "vault"
    ROUTER = "router"
    FACTORY = "factory"
    ORACLE = "oracle"
    GOVERNANCE = "governance"
    TIMELOCK = "timelock"
    MULTISIG = "multisig"
    EOA = "eoa"
    CLONE_CLASS = "clone_class"    # collapsed class of repeated clones
    UNKNOWN = "unknown"


class ProxyKind(StrEnum):
    NONE = "none"
    EIP1967_TRANSPARENT = "eip1967_transparent"
    EIP1967_UUPS = "eip1967_uups"
    EIP1822 = "eip1822"
    EIP1167_MINIMAL = "eip1167_minimal"   # clone
    BEACON = "beacon"
    DIAMOND = "diamond"                    # EIP-2535
    SAFE = "gnosis_safe"
    CUSTOM = "custom"


class EdgeType(StrEnum):
    IS_PROXY_FOR = "is_proxy_for"
    HOLDS_ROLE_OVER = "holds_role_over"
    READS_PRICE_FROM = "reads_price_from"
    CREATED_BY = "created_by"
    HOLDS_FUNDS = "holds_funds"
    HAS_ALLOWANCE = "has_allowance"
    DEPENDS_ON = "depends_on"              # references an address in storage/immutable
    CALLS = "calls"
    MIRRORS_DEPLOYMENT = "mirrors_deployment"  # same project on another chain (mirror)
    PEER_OF = "peer_of"                    # cross-chain messaging peer (LZ/bridge trusted remote)


def node_key(chain_id: int, addr: str | None) -> str | None:
    """Node key in the multi-chain graph: '<chain>:<addr>'."""
    a = norm_addr(addr)
    return f"{chain_id}:{a}" if a else None


# --------------------------------------------------------------------------- #
# Address utilities
# --------------------------------------------------------------------------- #

ZERO_ADDRESS = "0x" + "0" * 40


def norm_addr(addr: str | None) -> str | None:
    """Normalize an address to lowercase, 0x prefix, 42 characters."""
    if not addr:
        return None
    a = addr.lower().strip()
    if a.startswith("0x"):
        a = a[2:]
    a = a.rjust(40, "0")[-40:]
    return "0x" + a


def is_zero(addr: str | None) -> bool:
    return norm_addr(addr) in (None, ZERO_ADDRESS)


def addr_from_slot(word: str | None) -> str | None:
    """Extract an address from a 32-byte storage word (last 20 bytes)."""
    if not word:
        return None
    w = word.lower()
    if w.startswith("0x"):
        w = w[2:]
    if len(w) < 40 or set(w) == {"0"}:
        return None
    a = norm_addr("0x" + w[-40:])
    return None if is_zero(a) else a


# --------------------------------------------------------------------------- #
# Graph entities
# --------------------------------------------------------------------------- #

@dataclass
class Role:
    """Who controls what: owner / role-holder / admin."""
    name: str                       # "owner", "DEFAULT_ADMIN_ROLE", "proxyAdmin", ...
    holder: str | None = None    # address of the role holder
    source: str = ""                # how detected: "owner()", "RoleGranted log", "1967-admin-slot"


@dataclass
class ContractNode:
    address: str
    chain_id: int
    node_type: NodeType = NodeType.UNKNOWN
    source_tier: SourceTier = SourceTier.BYTECODE_ONLY
    proxy_kind: ProxyKind = ProxyKind.NONE
    implementation: str | None = None   # if proxy — logic address
    admin: str | None = None            # proxy admin (1967-admin / owner)
    beacon: str | None = None
    codehash: str | None = None
    name: str | None = None             # contract name from verified source
    roles: list[Role] = field(default_factory=list)
    state: dict[str, str] = field(default_factory=dict)   # meaningful slots: paused, fee, oracle...
    abi_present: bool = False
    is_scope: bool = True                  # in project scope vs external dependency
    membership: str = "member"             # member | candidate | external
    membership_score: float = 1.0          # 0..1 confidence of project membership
    token_role: str | None = None       # for tokens: own | reserved | transient
    deployer: str | None = None         # deployer address (creation tx)
    origin: str = "deterministic"       # deterministic | llm (provenance of discovery)
    notes: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.chain_id}:{self.address}"

    def __post_init__(self) -> None:
        self.address = norm_addr(self.address) or self.address
        self.implementation = norm_addr(self.implementation)
        self.admin = norm_addr(self.admin)
        self.beacon = norm_addr(self.beacon)


@dataclass
class CloneClass:
    """
    Collapsed class of repeated contracts (e.g. thousands of Uniswap pairs).
    Instead of thousands of nodes — one class: registration pattern + N samples + cap flag.
    """
    class_id: str                          # stable id (codehash or impl)
    codehash: str | None = None
    implementation: str | None = None   # for EIP-1167 clones
    factory: str | None = None
    registration: str = ""                 # "factory.createPair -> PairCreated"
    total_count: int = 0                   # how many were found in total
    sampled: list[str] = field(default_factory=list)  # example addresses (<= cap)
    capped: bool = False                   # whether the collection limit was reached
    node_type: NodeType = NodeType.CLONE_CLASS


@dataclass
class LogicalEntity:
    """
    An architecture entity WITHOUT an address (Morpho market = bytes32 storage in a singleton).
    Hyperedge: links the singleton parent to its real dependencies (oracle/irm/tokens).
    """
    id: str                                  # bytes32 hex (market id / other identifier)
    kind: str                                # "market" | ...
    parent: str                              # node_key of the singleton
    refs: list[str] = field(default_factory=list)  # node_keys of the real dependencies
    params: dict = field(default_factory=dict)


@dataclass
class Edge:
    """src/dst — node keys '<chain>:<addr>' (supports cross-chain edges)."""
    src: str
    dst: str
    edge_type: EdgeType
    label: str = ""
    origin: str = "deterministic"   # deterministic | llm (provenance of this relation)


@dataclass
class ArchitectureGraph:
    """Multi-chain graph: nodes keyed by '<chain>:<addr>'; chains listed in chains."""
    chains: list[int] = field(default_factory=list)
    roots: list[str] = field(default_factory=list)         # seed keys '<chain>:<addr>'
    nodes: dict[str, ContractNode] = field(default_factory=dict)
    clone_classes: list[CloneClass] = field(default_factory=list)
    logical: list[LogicalEntity] = field(default_factory=list)  # address-less entities (markets)
    edges: list[Edge] = field(default_factory=list)
    meta: dict = field(default_factory=dict)               # budget, timings, warnings

    # -- construction ------------------------------------------------------- #
    def add_node(self, node: ContractNode) -> ContractNode:
        if node.key in self.nodes:
            return self.nodes[node.key]
        self.nodes[node.key] = node
        if node.chain_id not in self.chains:
            self.chains.append(node.chain_id)
        return node

    def get_node(self, chain_id: int, addr: str) -> ContractNode | None:
        k = node_key(chain_id, addr)
        return self.nodes.get(k) if k else None

    def has_node(self, chain_id: int, addr: str) -> bool:
        return node_key(chain_id, addr) in self.nodes

    def add_edge(self, src_key: str, dst_key: str, edge_type: EdgeType, label: str = "",
                 origin: str = "deterministic") -> None:
        e = Edge(src_key, dst_key, edge_type, label, origin)
        if e.src and e.dst and e not in self.edges:
            self.edges.append(e)

    def warn(self, msg: str) -> None:
        self.meta.setdefault("warnings", []).append(msg)

    # -- serialization ------------------------------------------------------ #
    def to_dict(self) -> dict:
        return {
            "chains": self.chains,
            "roots": self.roots,
            "nodes": [asdict(n) for n in self.nodes.values()],
            "clone_classes": [asdict(c) for c in self.clone_classes],
            "logical": [asdict(le) for le in self.logical],
            "edges": [asdict(e) for e in self.edges],
            "meta": self.meta,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    # -- brief summary ------------------------------------------------------ #
    def summary(self) -> str:
        by_type: dict[str, int] = {}
        for n in self.nodes.values():
            by_type[n.node_type.value] = by_type.get(n.node_type.value, 0) + 1
        by_member: dict[str, int] = {}
        by_token_role: dict[str, int] = {}
        for n in self.nodes.values():
            by_member[n.membership] = by_member.get(n.membership, 0) + 1
            if n.token_role:
                by_token_role[n.token_role] = by_token_role.get(n.token_role, 0) + 1
        lines = [
            f"chains={self.chains}  nodes={len(self.nodes)}  "
            f"clone_classes={len(self.clone_classes)}  edges={len(self.edges)}",
            "  types: " + ", ".join(f"{k}={v}" for k, v in sorted(by_type.items())),
            "  membership: " + ", ".join(f"{k}={v}" for k, v in sorted(by_member.items())),
        ]
        if by_token_role:
            lines.append("  tokens: " + ", ".join(f"{k}={v}" for k, v in sorted(by_token_role.items())))
        price_reads = sum(1 for e in self.edges if e.edge_type == EdgeType.READS_PRICE_FROM)
        custody = sum(1 for e in self.edges if e.edge_type == EdgeType.HOLDS_FUNDS)
        if price_reads or custody:
            lines.append(f"  relations: reads_price_from={price_reads}, holds_funds={custody}")
        anom = self.meta.get("anomalies") or []
        if anom:
            high = sum(1 for a in anom if a.get("severity") == "high")
            lines.append(f"  anomalies: {len(anom)} ({high} high; see --anomalies)")
        # membership precision proxy (lazy import — audit lives in a sibling module)
        from .audit import membership_audit
        au = membership_audit(self)
        lines.append(f"  precision≈{au.precision_proxy} (leaked {au.leaked_members}/{au.total_members} members)")
        if self.clone_classes:
            for c in self.clone_classes:
                lines.append(
                    f"  clone-class {c.class_id[:14]}… total={c.total_count} "
                    f"sampled={len(c.sampled)} capped={c.capped} [{c.registration}]"
                )
        if self.meta.get("family"):
            lines.append(f"  family (llm): {self.meta['family']}")
        if self.meta.get("at_block") is not None:
            lines.append(f"  pinned at block {self.meta['at_block']}")
        diag = self.meta.get("diagnostics")
        if diag:
            counts = ", ".join(f"{k}={v}" for k, v in diag.items() if k != "samples")
            lines.append(f"  ⚠ diagnostics: {counts}")
        for w in self.meta.get("warnings", []):
            lines.append(f"  ⚠ {w}")
        return "\n".join(lines)
