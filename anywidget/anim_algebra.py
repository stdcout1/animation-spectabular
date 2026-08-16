"""
Animation algebra: derive SVG transitions by diffing two rendered formal
states, instead of hand-writing widget[key] = (fn, "tween"/"snap") bindings
per element.

    svg_generator(state, recipe, base_svg): state -> concrete svg frame
    svg_diff(svg_a, svg_b): two frames -> Leaf animation
    animate_trace(states, recipe, base_svg): a scenario -> one Animation

Animations combine with two operators:

    a + b   sequential composition ("+"). Associative, NOT commutative.
            Identity is E (the empty animation).
    a | b   parallel composition ("|") of two animations touching
            disjoint svg ids: they play simultaneously. Raises
            AnimationConflict if their touched ids overlap.

Both operators always normalize their result (see `seq`/`par`): a Seq
never contains a Seq child, a Par never contains a Par branch, and if
every branch of a Par shares a common leading/trailing sub-sequence,
`par()` factors it back out, so `(a1+b) | (a2+b)` and `(a1|a2)+b`
normalize to the identical structure. That normal form is what makes the
distributive law hold by construction, and it's also why the
disjointness check only runs on the part that's genuinely different
between branches: a shared, identically timed suffix/prefix can never be
a real conflict, so it's factored out before the check runs. See
assert_laws() at the bottom for the checked laws.
"""
from __future__ import annotations

import copy
import itertools
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, FrozenSet, Optional, Tuple

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)

# Presentation attributes SMIL can interpolate numerically/by color.
# transform is handled separately (structured op), not as a plain string.
ANIMATABLE = {
    "x", "y", "cx", "cy", "r", "width", "height",
    "fill", "stroke", "opacity", "fill-opacity", "stroke-opacity",
}

_TRANSFORM_ARITY = {"translate": 2, "rotate": 3, "scale": 2}


class AnimationConflict(Exception): 
    """Animation Conflict"""

# The Op / Leaf / Seq / Par AST

@dataclass(frozen=True)
class Op:
    kind: str  # "tween" | "snap" | "add" | "remove" | "reparent"
    id: str
    attr: Optional[str] = None
    old: Any = None  # str, or ("translate"/"rotate"/"scale", (float, ...)), or None
    new: Any = None
    parent_id: Optional[str] = None  # add: new element's parent id (None = root); reparent: new parent id
    elem_xml: Optional[str] = None  # add: serialized subtree to insert

class Animation:
    """Common base for Leaf/Seq/Par. Never construct Seq/Par directly --
    always go through +, |, or the seq()/par() smart constructors, which
    keep every Animation in normal form."""

    def __add__(self, other: "Animation") -> "Animation":
        return seq(self, other)

    def __or__(self, other: "Animation") -> "Animation":
        return par(self, other)

    @property
    def touched_ids(self) -> FrozenSet[str]:
        raise NotImplementedError

@dataclass(frozen=True)
class Leaf(Animation):
    ops: FrozenSet[Op] = field(default_factory=frozenset)

    @property
    def touched_ids(self) -> FrozenSet[str]:
        return frozenset(op.id for op in self.ops)

@dataclass(frozen=True)
class Seq(Animation):
    children: Tuple[Animation, ...] = ()

    @property
    def touched_ids(self) -> FrozenSet[str]:
        return frozenset().union(*(c.touched_ids for c in self.children)) if self.children else frozenset()

@dataclass(frozen=True)
class Par(Animation):
    branches: Tuple[Animation, ...] = ()

    @property
    def touched_ids(self) -> FrozenSet[str]:
        return frozenset().union(*(b.touched_ids for b in self.branches)) if self.branches else frozenset()


E = Seq(())  # identity for +


def is_identity(a: Animation) -> bool:
    return (isinstance(a, Seq) and not a.children) or (isinstance(a, Leaf) and not a.ops)


def _sort_key(a: Animation):
    # deterministic ordering for Par branches (disjoint parallel merge
    # doesn't care about branch order, so we canonicalize it away instead
    # of treating a|b and b|a as structurally different)
    return (tuple(sorted(a.touched_ids)), repr(a))


def _as_children(a: Animation) -> Tuple[Animation, ...]:
    return a.children if isinstance(a, Seq) else (a,)


def _from_children(children: Tuple[Animation, ...]) -> Animation:
    if not children:
        return E
    if len(children) == 1:
        return children[0]
    return Seq(children)


def seq(*items: Animation) -> Animation:
    # A Seq may freely contain a Par as one of its children (do a, then
    # b|c together, then d), so no distribution happens here. This only
    # flattens: a Seq never nests a Seq.
    flat = []
    for it in items:
        if is_identity(it):
            continue
        flat.extend(_as_children(it)) if isinstance(it, Seq) else flat.append(it)
    return _from_children(tuple(flat))


def _factor_common(branches: Tuple[Animation, ...]):
    # If every branch shares a common leading and/or trailing
    # sub-sequence, peel it out, e.g.
    # Par(Seq(a1, b), Seq(a2, b)) -> prefix=(), core=(a1, a2), suffix=(b,)
    # This makes (a1+b)|(a2+b) re-normalize to the same thing as
    # (a1|a2)+b (see par() below)
    lists = [list(_as_children(b)) for b in branches]
    n = min(len(l) for l in lists)

    prefix_len = 0
    for i in range(n):
        if len({lists[j][i] for j in range(len(lists))}) == 1:
            prefix_len += 1
        else:
            break

    suffix_len = 0
    for i in range(1, n - prefix_len + 1):
        if len({lists[j][-i] for j in range(len(lists))}) == 1:
            suffix_len += 1
        else:
            break

    prefix = tuple(lists[0][:prefix_len])
    suffix = tuple(lists[0][len(lists[0]) - suffix_len:]) if suffix_len else ()
    cores = tuple(_from_children(tuple(l[prefix_len:len(l) - suffix_len])) for l in lists)
    return prefix, cores, suffix


def par(*items: Animation) -> Animation:
    flat = []
    for it in items:
        if is_identity(it):
            continue
        flat.extend(it.branches) if isinstance(it, Par) else flat.append(it)
    if not flat:
        return E
    if len(flat) == 1:
        return flat[0]

    prefix, cores, suffix = _factor_common(tuple(flat))
    if prefix or suffix:
        return seq(*prefix, par(*cores), *suffix)

    all_ids = [tid for br in flat for tid in br.touched_ids]
    dupes = [tid for tid, n in Counter(all_ids).items() if n > 1]
    if dupes:
        raise AnimationConflict(
            f"parallel (|) branches both touch id(s) {dupes!r} at possibly different "
            "times: give them disjoint svg ids/attributes, or sequence them with + instead"
        )
    return Par(tuple(sorted(flat, key=_sort_key)))


# --------------------------------------------------------------------------
# svg_diff: two rendered frames -> a Leaf animation
# --------------------------------------------------------------------------


def _local_name(tag: str) -> str:
    return tag.split("}")[-1]


def _strip_anonymous(root: ET.Element) -> None:
    # Each parent's children are copied into a plain list before removing
    # from them. Removing elements from a list while iterating it directly
    # skips every other element instead of removing all of them.
    for parent in root.iter():
        for child in list(parent):
            if child.get("id") is None:
                parent.remove(child)


def _collect_anonymous(root: ET.Element):
    return [copy.deepcopy(el) for el in root.iter() if el is not root and el.get("id") is None]


def _build_id_map(root: ET.Element):
    ids = {}
    for el in root.iter():
        eid = el.get("id")
        if eid is not None:
            if eid in ids:
                raise ValueError(f"duplicate svg id: {eid!r}")
            ids[eid] = el
    return ids


def _parent_map(root: ET.Element):
    return {child: parent for parent in root.iter() for child in parent}


def _nearest_id_ancestor(el, parent_of) -> Optional[str]:
    p = parent_of.get(el)
    while p is not None:
        pid = p.get("id")
        if pid is not None:
            return pid
        p = parent_of.get(p)
    return None


def _parse_transform(el) -> Optional[Tuple[str, Tuple[float, ...]]]:
    t = el.get("transform")
    if not t or "(" not in t:
        return None
    kind, _, rest = t.partition("(")
    kind = kind.strip()
    if kind not in _TRANSFORM_ARITY:
        return None  # composite/matrix() transform: opaque, handled as a snap
    try:
        args = tuple(float(x) for x in rest.rstrip(")").replace(",", " ").split())
    except ValueError:
        return None
    if len(args) != _TRANSFORM_ARITY[kind]:
        return None
    return (kind, args)


def _compare_common(eid: str, a_el, b_el) -> set:
    ops = set()

    if (a_el.text or "") != (b_el.text or ""):
        # text content, like FormalVizWidget's "text" pseudo-property:
        # never animated (SMIL text-content isn't reliable cross-browser),
        # always a snap
        ops.add(Op("snap", eid, "text", a_el.text, b_el.text))

    a_raw_t, b_raw_t = a_el.get("transform"), b_el.get("transform")
    if a_raw_t != b_raw_t:
        a_t, b_t = _parse_transform(a_el), _parse_transform(b_el)
        if a_t is not None and b_t is not None and a_t[0] == b_t[0]:
            ops.add(Op("tween", eid, "transform", a_t, b_t))
        else:
            # kind changed (e.g. rotate -> translate) or one side is an
            # opaque matrix() transform: can't interpolate, snap instead
            ops.add(Op("snap", eid, "transform", a_raw_t, b_raw_t))

    for attr in (set(a_el.keys()) | set(b_el.keys())) - {"id", "transform"}:
        a_val, b_val = a_el.get(attr), b_el.get(attr)
        if a_val == b_val:
            continue
        if attr in ANIMATABLE and a_val is not None and b_val is not None:
            ops.add(Op("tween", eid, attr, a_val, b_val))
        else:
            # not animatable, or the attribute was added/removed outright
            # (a_val/b_val is None): snapped, never silently dropped
            ops.add(Op("snap", eid, attr, a_val, b_val))

    return ops


def _add_op(eid: str, b_el, anchor: Optional[str]) -> Op:
    return Op("add", eid, parent_id=anchor, elem_xml=ET.tostring(b_el, encoding="unicode"))


def svg_diff(svg_a: str, svg_b: str) -> Animation:
    """
    Diff two rendered SVG frames (as produced by svg_generator for two
    formal states) into an animation: the minimal set of per-id ops that
    turns frame A into frame B, matching elements by `id`. Returns E (the
    identity) if nothing changed.

    Elements without an id are not individually addressable/diffable, so
    they can't be matched up and attribute-diffed like id'd elements can.
    Any of B's no-id elements that are a match for one of
    A's is left alone, since it's already sitting in whatever base frame
    the result gets rendered against. Anything else new in B is inserted
    as a new visible element: there's no way to tell it
    apart from new versus moved/reordered, so it's always
    treated as new. No-id content that existed in A but has no match in B
    is left in place.
    """
    root_a, root_b = ET.fromstring(svg_a), ET.fromstring(svg_b)
    anonymous_a_xml = {ET.tostring(el, encoding="unicode") for el in _collect_anonymous(root_a)}
    _strip_anonymous(root_a)
    anonymous_b = [el for el in _collect_anonymous(root_b)
                   if ET.tostring(el, encoding="unicode") not in anonymous_a_xml]

    ids_a, ids_b = _build_id_map(root_a), _build_id_map(root_b)
    ids_a.pop(root_a.get("id"), None)
    ids_b.pop(root_b.get("id"), None)

    parent_of_a, parent_of_b = _parent_map(root_a), _parent_map(root_b)

    common = ids_a.keys() & ids_b.keys()
    deleted = ids_a.keys() - ids_b.keys()
    added = ids_b.keys() - ids_a.keys()

    ops = set()

    for eid in common:
        a_el, b_el = ids_a[eid], ids_b[eid]
        if _local_name(a_el.tag) != _local_name(b_el.tag):
            # tag changed (e.g. circle -> rect): attributes don't
            # correspond across element types, so this is a
            # remove-old/add-new, not an attribute-level compare
            anchor = _nearest_id_ancestor(b_el, parent_of_b)
            ops.add(Op("remove", eid))
            ops.add(_add_op(eid, b_el, anchor if anchor in ids_a else None))
            continue
        ops |= _compare_common(eid, a_el, b_el)
        a_anchor = _nearest_id_ancestor(a_el, parent_of_a)
        b_anchor = _nearest_id_ancestor(b_el, parent_of_b)
        if a_anchor != b_anchor:
            # same id, same tag, but moved to a different parent: can't
            # meaningfully tween across a coordinate-system change, so
            # this is a snap-class reparent, not an attribute diff
            ops.add(Op("reparent", eid, parent_id=b_anchor))

    for eid in deleted:
        ops.add(Op("remove", eid))

    # Only the outermost new id in a freshly added subtree gets an "add"
    # op. Otherwise a new group containing new nested ids would be
    # inserted once as the group's own subtree and again per nested id,
    # duplicating content. Nested new ids ride along inside their
    # top-level ancestor's serialized elem_xml.
    for eid in added:
        el = ids_b[eid]
        p = parent_of_b.get(el)
        nested_in_added = False
        while p is not None:
            pid = p.get("id")
            if pid is not None:
                nested_in_added = pid in added
                break
            p = parent_of_b.get(p)
        if nested_in_added:
            continue
        anchor = _nearest_id_ancestor(el, parent_of_b)
        ops.add(_add_op(eid, el, anchor if anchor in ids_a else None))

    for i, el in enumerate(anonymous_b):
        ops.add(Op("add", f"~anon{i}", parent_id=None, elem_xml=ET.tostring(el, encoding="unicode")))

    return Leaf(frozenset(ops)) if ops else E


# svg_generator: formal state -> one concrete rendered frame

def _fmt_num(x) -> str:
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return f"{x:.6f}".rstrip("0").rstrip(".")


def svg_generator(state: dict, recipe: dict, base_svg: str) -> str:
    """
    Render one concrete SVG frame for `state`. `recipe` is a plain
    {"selector.prop": fn} table: the same fn(state) -> value functions
    already written as widget[key] = (fn, method) bindings in
    Elevator.ipynb/Automotive.ipynb, just without the method tag.
    tween-vs-snap is no longer picked by hand; svg_diff infers it by
    comparing two frames produced by this function.
    """
    root = ET.fromstring(base_svg)
    by_id = {el.get("id"): el for el in root.iter() if el.get("id")}
    for key, fn in recipe.items():
        selector, prop = key.rsplit(".", 1)
        el = by_id.get(selector)
        if el is None:
            continue
        value = fn(state)
        if prop == "text":
            el.text = str(value)
        elif prop.startswith("attr:"):
            el.set(prop[len("attr:"):], str(value))
        elif prop == "transform":
            kind, args = value
            el.set("transform", f"{kind}({' '.join(_fmt_num(a) for a in args)})")
        else:
            el.set(prop, str(value))
    return ET.tostring(root, encoding="unicode")


def animate_trace(states, recipe: dict, base_svg: str) -> Animation:
    """A full scenario's animation: left-fold + over consecutive-frame diffs."""
    frames = [svg_generator(s, recipe, base_svg) for s in states]
    anim: Animation = E
    for a, b in zip(frames, frames[1:]):
        anim = anim + svg_diff(a, b)
    return anim


# compile_to_svg: render an Animation as one static, playable SMIL svg,
# purely for visual inspection in the demo notebook. usefull for html export

def _find_parent(root, el):
    for p in root.iter():
        if el in list(p):
            return p
    return None


def _emit_op(op: Op, by_id: dict, root, anim_id: str, begin: str, dur: float) -> None:
    if op.attr == "text":
        # Text is never animated (SMIL text content isn't reliable
        # cross-browser, same convention as FormalVizWidget's "text"
        # pseudo-property), so the final value is baked in directly. This
        # ignores `begin` entirely: unlike every other op kind, a text
        # change is applied at compile time rather than at its scheduled
        # point in the sequence, since SMIL has no declarative way to
        # defer a textContent write. A static preview can therefore show
        # a label that's already ahead of where the rest of the
        # animation visually is. A live player would need a scripted
        # trigger to defer it properly.
        el = by_id.get(op.id)
        if el is not None:
            el.text = op.new
        return

    if op.attr == "transform":
        el = by_id.get(op.id)
        if el is None:
            return
        smil = ET.SubElement(el, "animateTransform")
        smil.set("id", anim_id)
        smil.set("attributeName", "transform")
        if op.kind == "tween" and isinstance(op.old, tuple) and isinstance(op.new, tuple) and op.old[0] == op.new[0]:
            kind, oargs = op.old
            _, nargs = op.new
            smil.set("type", kind)
            smil.set("from", " ".join(_fmt_num(a) for a in oargs))
            smil.set("to", " ".join(_fmt_num(a) for a in nargs))
            smil.set("dur", f"{dur}s")
        else:
            kind, args = op.new if isinstance(op.new, tuple) else ("translate", (0, 0))
            smil.set("type", kind)
            smil.set("from", " ".join(_fmt_num(a) for a in args))
            smil.set("to", " ".join(_fmt_num(a) for a in args))
            smil.set("dur", "0.001s")
        smil.set("begin", begin)
        smil.set("fill", "freeze")
        return

    if op.kind == "tween":
        el = by_id.get(op.id)
        if el is None:
            return
        smil = ET.SubElement(el, "animate")
        smil.set("id", anim_id)
        smil.set("attributeName", op.attr)
        smil.set("from", str(op.old))
        smil.set("to", str(op.new))
        smil.set("dur", f"{dur}s")
        smil.set("begin", begin)
        smil.set("fill", "freeze")
        return

    if op.kind == "snap":
        el = by_id.get(op.id)
        if el is None:
            return
        smil = ET.SubElement(el, "animate")
        smil.set("id", anim_id)
        smil.set("attributeName", op.attr)
        val = str(op.new) if op.new is not None else str(op.old)
        smil.set("from", val)
        smil.set("to", val)
        smil.set("dur", "0.001s")
        smil.set("begin", begin)
        smil.set("fill", "freeze")
        return

    if op.kind == "remove":
        el = by_id.get(op.id)
        if el is None:
            return
        smil = ET.SubElement(el, "animate")
        smil.set("id", anim_id)
        smil.set("attributeName", "opacity")
        smil.set("from", el.get("opacity", "1"))
        smil.set("to", "0")
        smil.set("dur", f"{dur}s")
        smil.set("begin", begin)
        smil.set("fill", "freeze")
        return

    if op.kind == "add":
        parent = (by_id.get(op.parent_id) if op.parent_id else None) or root
        new_el = ET.fromstring(op.elem_xml)
        final_opacity = new_el.get("opacity", "1")
        new_el.set("opacity", "0")
        parent.append(new_el)
        by_id[op.id] = new_el
        smil = ET.SubElement(new_el, "animate")
        smil.set("id", anim_id)
        smil.set("attributeName", "opacity")
        smil.set("from", "0")
        smil.set("to", final_opacity)
        smil.set("dur", f"{dur}s")
        smil.set("begin", begin)
        smil.set("fill", "freeze")
        return

    if op.kind == "reparent":
        el = by_id.get(op.id)
        new_parent = (by_id.get(op.parent_id) if op.parent_id else None) or root
        if el is None or new_parent is None:
            return
        old_parent = _find_parent(root, el)
        if old_parent is not None and new_parent is not old_parent:
            old_parent.remove(el)
            new_parent.append(el)
        return


def compile_to_svg(anim: Animation, base_svg: str, leaf_dur: float = 1.0) -> str:
    root = ET.fromstring(base_svg)
    by_id = {el.get("id"): el for el in root.iter() if el.get("id")}
    uid = itertools.count()

    def emit(a: Animation, begin: str) -> str:
        # returns a SMIL id-ref marking when `a` finishes, so a following
        # Seq sibling can chase it via begin="<that id>.end"
        if isinstance(a, Leaf):
            end_id = None
            for op in a.ops:
                anim_id = f"a{next(uid)}"
                end_id = end_id or anim_id
                _emit_op(op, by_id, root, anim_id, begin, leaf_dur)
            return f"{end_id}.end" if end_id else begin
        if isinstance(a, Seq):
            cur = begin
            for child in a.children:
                cur = emit(child, cur)
            return cur
        if isinstance(a, Par):
            ends = [emit(branch, begin) for branch in a.branches]
            return ends[0] if ends else begin
        raise TypeError(a)

    emit(anim, "0s")
    return ET.tostring(root, encoding="unicode")


# assert_laws: tests


def _leaf(*ids: str, attr: str = "fill", old: str = "red", new: str = "blue") -> Leaf:
    return Leaf(frozenset(Op("snap", i, attr, old, new) for i in ids))


def assert_laws() -> None:
    a, b, c = _leaf("a"), _leaf("b"), _leaf("c")

    # + is associative
    assert (a + b) + c == a + (b + c), "+ is not associative"

    # + is not commutative
    assert a + b != b + a, "+ should not be commutative"

    # E is the identity for +
    assert a + E == a == E + a, "E is not an identity for +"

    # | requires disjoint ids, and raises when two branches
    # disagree about the same id. Identical branches merge idempotently
    # instead, see the a|a case just below: that's not a conflict.
    try:
        _leaf("x", new="blue") | _leaf("x", new="green")
    except AnimationConflict:
        pass
    else:
        raise AssertionError("expected AnimationConflict for conflicting ops on the same id in |")

    # identical branches are idempotent, not a conflict
    same = _leaf("x")
    assert same | same == same, "a | a should collapse to a"

    # | is associative over disjoint branches
    p1, p2, p3 = _leaf("p1"), _leaf("p2"), _leaf("p3")
    assert (p1 | p2) | p3 == p1 | (p2 | p3), "| is not associative"

    # (a1 | a2) + b == (a1 + b) | (a2 + b): left distributivity
    a1, a2, bb = _leaf("x1"), _leaf("x2"), _leaf("y")
    lhs = (a1 | a2) + bb
    rhs = (a1 + bb) | (a2 + bb)
    assert lhs == rhs, "left distributivity of + over | failed"

    # b + (a1 | a2) == (b + a1) | (b + a2): right distributivity
    lhs2 = bb + (a1 | a2)
    rhs2 = (bb + a1) | (bb + a2)
    assert lhs2 == rhs2, "right distributivity of + over | failed"

    # sanity: svg_diff of a state against itself is the identity
    svg = '<svg xmlns="http://www.w3.org/2000/svg"><circle id="c" cx="1" cy="2" r="3"/></svg>'
    assert svg_diff(svg, svg) == E, "diffing identical frames should yield the identity animation"

    print("all algebra laws verified")
