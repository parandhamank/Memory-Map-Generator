#!/usr/bin/env python3
import json
import argparse
from dataclasses import dataclass, field
from typing import Any, Dict, List, Union

NumberLike = Union[int, str]


def parse_int(x: NumberLike) -> int:
    if isinstance(x, int):
        return x
    if isinstance(x, str):
        s = x.strip().lower()
        if s.startswith("0x"):
            return int(s, 16)
        return int(s, 10)
    raise TypeError(f"Unsupported number type: {type(x)}")


@dataclass
class Node:
    name: str
    start: int
    size: int
    children: List["Node"] = field(default_factory=list)

    @property
    def end(self) -> int:
        return self.start + self.size


def build_node(d: Dict[str, Any]) -> Node:
    name = d.get("name", "Unnamed")
    start = parse_int(d["start"])
    size = parse_int(d["size"])
    children = [build_node(c) for c in (d.get("children") or [])]
    children.sort(key=lambda n: n.start)
    return Node(name=name, start=start, size=size, children=children)


def validate_tree(n: Node, path="root") -> List[str]:
    errs: List[str] = []
    kids = n.children

    for c in kids:
        if c.start < n.start or c.end > n.end:
            errs.append(
                f"{path}/{n.name}: child '{c.name}' [{hex(c.start)}..{hex(c.end)}] "
                f"outside parent [{hex(n.start)}..{hex(n.end)}]"
            )
        errs.extend(validate_tree(c, f"{path}/{n.name}"))

    for i in range(len(kids) - 1):
        a, b = kids[i], kids[i + 1]
        if a.end > b.start:
            errs.append(f"{path}/{n.name}: overlap between '{a.name}' and '{b.name}'")

    return errs


def flatten(n: Node, depth=0, parent_id="") -> List[Dict[str, Any]]:
    node_id = (parent_id + "/" + f"{n.name}@{hex(n.start)}").strip("/")
    out = [{
        "id": node_id,
        "name": n.name,
        "start": n.start,
        "size": n.size,
        "end": n.end,
        "depth": depth,
        "parent": parent_id if parent_id else None
    }]
    for c in n.children:
        out.extend(flatten(c, depth + 1, node_id))
    return out


HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Memory Map</title>
<style>
  :root{
    --border:#bdbdbd;
    --lineGrey:#9a9a9a;   /* marker line + pill border, everywhere */

    --stackBorderW: 2px;  /* keep in sync with .stack border */
    --innerBorderW: 1px;  /* keep in sync with .innerStack border */

    --tickT: 2px;
    --tickInnerT: 2px;

    --text:#1b1b1b;
    --sel:#2b2b2b;

    --markerCol: 280px;
    --markerGap: 16px;

    --innerLaneW: 120px;
    --innerLaneGap: 0px;

    --tickW: 34px;

    --gapFill:#efefef;
    --gapText:#222;

    --d0:#c9b78e;
    --d1:#c2d3c5;
    --d2:#c9cfe8;
    --d3:#e6c8df;
    --d4:#d6c7b8;

    --sepSoft: rgba(0,0,0,0.22);
  }

  body{ margin:0; font-family:system-ui,Segoe UI,Arial; color:var(--text); background:#fff; }

  header{
    position: sticky;
    top: 0;
    z-index: 1000;
    padding: 12px 16px;
    border-bottom: 1px solid rgba(255,255,255,0.18);
    background: linear-gradient(90deg, #0b1220 0%, #1e40af 55%, #0891b2 100%);
    color: #fff;
    box-shadow: 0 6px 20px rgba(0,0,0,0.18);
  }
  .bar{
    display:grid;
    grid-template-columns: auto 1fr auto;
    align-items:center;
    gap:12px;
  }
  .barLeft{ display:flex; gap:10px; align-items:center; }
  .barTitle{
    justify-self:center;
    font-weight: 900;
    font-size: 18px;
    letter-spacing: 0.3px;
    color: #fff;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    padding: 8px 14px;
    border-radius: 999px;
    background: rgba(255,255,255,0.12);
    border: 1px solid rgba(255,255,255,0.18);
    text-shadow: 0 1px 0 rgba(0,0,0,0.28);
    backdrop-filter: blur(8px);
  }
  button{
    padding: 7px 12px;
    border-radius: 12px;
    border: 1px solid rgba(255,255,255,0.22);
    background: rgba(255,255,255,0.10);
    color: #fff;
    cursor: pointer;
    font-weight: 750;
    box-shadow: 0 1px 0 rgba(0,0,0,0.10);
    backdrop-filter: blur(8px);
    transition: transform 80ms ease, background 120ms ease;
  }
  button:hover{ background: rgba(255,255,255,0.18); }
  button:active{ transform: translateY(1px); background: rgba(255,255,255,0.22); }

  .wrap{ padding:14px; height: calc(100vh - 64px); overflow:auto; }
  .diagram{ display:grid; grid-template-columns: min(1020px, 100%); justify-content:center; }
  .stackWrap{ position: relative; }

  .stack{
    border: var(--stackBorderW) solid var(--border);
    border-radius: 10px;
    overflow: visible;
    background: #f7f7f7;
    display:flex;
    flex-direction:column;
    position: relative;
    height: auto;
  }

  .slice{
    position: relative;
    border-bottom: 2px solid var(--sepSoft);
    background: var(--d0);
    display:flex;
    align-items:center;
    justify-content:center;
    box-sizing:border-box;
    cursor:pointer;
    user-select:none;
    flex: 0 0 auto;
  }
  .slice:last-child{ border-bottom:none; }
  .slice.gap{ background: var(--gapFill); cursor: default; }
  .slice.gap .name{ color: var(--gapText); font-weight:700; }
  .slice.selected{ outline: 2px solid var(--sel); outline-offset: -2px; }

  .label{ text-align:center; max-width: 92%; padding: 6px 10px; box-sizing:border-box; }
  .name{ font-weight: 750; font-size: 14px; line-height: 1.1; }

  .markerR{
    position:absolute;
    right: calc(-1 * var(--markerCol));
    width: calc(var(--markerCol) - var(--markerGap));
    top: 50%;
    margin-top: -10px;
    display:flex;
    justify-content:flex-start;
    white-space:nowrap;
    pointer-events:none;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
    font-size: 12px;
    font-weight: 700;
    color:#444;
    z-index: 10;
  }
  .sizeTag{
    background:#fff;
    border:1px solid #d0d0d0;
    border-radius: 8px;
    padding: 2px 8px;
    box-shadow: 0 1px 0 rgba(0,0,0,0.03);
  }

  .sizeIn{
    position:absolute;
    right: 10px;
    top: 50%;
    transform: translateY(-50%);
    background:#fff;
    border:1px solid #d0d0d0;
    border-radius: 8px;
    padding: 2px 8px;
    box-shadow: 0 1px 0 rgba(0,0,0,0.03);
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
    font-size: 12px;
    font-weight: 800;
    color:#444;
    pointer-events:none;
    white-space:nowrap;
  }

  /* OUTER marker layer aligned to OUTER BORDER EDGE */
  .markerLayerOuter{
    position:absolute;
    left: calc(-1 * var(--markerCol) - var(--stackBorderW));
    top: calc(-1 * var(--stackBorderW));
    width: calc(var(--markerCol) + var(--stackBorderW));
    height: calc(100% + 2 * var(--stackBorderW));
    pointer-events:none;
    z-index: 30;
  }
  .boundaryOuter{ position:absolute; left:0; right:0; height:0; }

  .boundaryOuter .tick{
    position:absolute;
    right: 0px;
    top: calc(-1 * (var(--tickT) / 2));
    width: var(--tickW);
    height: var(--tickT);
    background: var(--lineGrey);
    opacity: 1;
  }

  .boundaryOuter .markerPill{
    position:absolute;
    right: calc(var(--tickW));
    top: 0;
    transform: translateY(-50%);
    border-radius: 999px;
    padding: 2px 10px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
    font-size: 12.5px;
    font-weight: 900;
    white-space: nowrap;
    border: 2px solid var(--lineGrey);
    color: rgba(0,0,0,0.82);
    box-shadow: 0 1px 0 rgba(0,0,0,0.06);
  }

  .inner{
    position:absolute;
    inset: 0;
    padding: 10px 22px 10px 10px;
    box-sizing:border-box;
    display:none;
    overflow: visible;
  }
  .slice.expanded > .inner{ display:block; }
  .slice.expanded > .label{ display:none; }

  .innerShell{
    width: 100%;
    display:flex;
    gap: var(--innerLaneGap);
    align-items: flex-start;
  }
  .innerLane{
    width: var(--innerLaneW);
    flex: 0 0 var(--innerLaneW);
    position: relative;
    align-self: flex-start;
  }
  .innerStack{
    flex: 1 1 auto;
    border: var(--innerBorderW) solid rgba(0,0,0,0.28);
    border-radius: 10px;
    background:#fdfdfd;
    display:flex;
    flex-direction:column;
    position: relative;
    overflow: visible;
    align-self: flex-start;
  }

  .innerSlice{
    position:relative;
    border-bottom: 2px solid var(--sepSoft);
    display:flex;
    align-items:center;
    justify-content:center;
    box-sizing:border-box;
    cursor:pointer;
    user-select:none;
    flex: 0 0 auto;
  }
  .innerSlice:last-child{ border-bottom:none; }
  .innerSlice.gap{ background: var(--gapFill) !important; cursor:default; }
  .innerSlice.gap .name{ color: var(--gapText); font-weight:700; }
  .innerSlice.selected{ outline:2px solid var(--sel); outline-offset:-2px; }
  .innerSlice .name{ font-size: 13px; }

  .laneBoundary{ position:absolute; left:0; right:0; height:0; }

  .laneBoundary .markerPill{
    position:absolute;
    right: calc(var(--tickW));
    top:0;
    transform: translateY(-50%);
    border-radius: 999px;
    padding: 2px 10px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
    font-size: 12.5px;
    font-weight: 900;
    white-space: nowrap;
    border: 2px solid var(--lineGrey);
    color: rgba(0,0,0,0.82);
    box-shadow: 0 1px 0 rgba(0,0,0,0.06);
  }

  .laneBoundary .tick{
    position:absolute;
    right: 0px;
    top: calc(-1 * (var(--tickInnerT) / 2));
    width: var(--tickW);
    height: var(--tickInnerT);
    background: var(--lineGrey);
    opacity: 1;
  }

  .depth-0{ background: var(--d0); }
  .depth-1{ background: var(--d1); }
  .depth-2{ background: var(--d2); }
  .depth-3{ background: var(--d3); }
  .depth-4{ background: var(--d4); }
</style>
</head>
<body>
<header>
  <div class="bar">
    <div class="barLeft">
      <button id="collapseAllBtn">Collapse all</button>
      <button id="expandAllBtn">Expand all</button>
    </div>
    <div class="barTitle" id="pageTitle">Memory Map</div>
    <div></div>
  </div>
</header>

<div class="wrap">
  <div class="diagram">
    <div class="stackWrap">
      <div class="stack" id="stack"></div>
    </div>
  </div>
</div>

<script>
const DATA = __DATA_JSON__;
const nodes = DATA.nodes;
const byId = new Map(nodes.map(n => [n.id, n]));

/* Layout constants */
const GAP_PX_OUTER = 52;  // keep as-is
const GAP_PX_INNER = 44;  // keep as-is
const MIN_PX = GAP_PX_OUTER;
const MIN_PX_INNER = GAP_PX_INNER;

/* Inner padding (match CSS .inner padding-top/bottom) */
const INNER_PAD_TOP = 10;
const INNER_PAD_BOTTOM = 10;
const INNER_PAD_Y = INNER_PAD_TOP + INNER_PAD_BOTTOM;

/* Title */
document.getElementById("pageTitle").textContent = DATA.root.name || "Memory Map";
document.title = DATA.root.name ? DATA.root.name : "Memory Map";

/* Utils */
function fmtSize(n){
  const units = ["B","KB","MB","GB","TB"];
  let v = n, i = 0;
  while (v >= 1024 && i < units.length-1){ v/=1024; i++; }
  return (i===0 ? v.toFixed(0) : v.toFixed(2)) + " " + units[i];
}
function hex(n){
  let s = n.toString(16).toUpperCase();
  if (s.length < 8) s = s.padStart(8, "0");
  s = s.replace(/(.{4})(?=.)/g, "$1_");
  return "0x" + s;
}
function yKey(y){ return Math.round(y); }

function childrenOf(parentId){
  return nodes.filter(n => n.parent === parentId).sort((a,b)=>a.start-b.start);
}
function hasChildren(id){ return childrenOf(id).length > 0; }

/* Gaps */
function gapsFromChildren(root, kids){
  if (kids.length === 0) return [];
  const gaps = [];
  let cur = root.start;
  for (const k of kids){
    if (k.start > cur){
      gaps.push({ id: root.id + "/gap@" + cur, name:"Unmapped / Reserved",
        start:cur, end:k.start, size:k.start-cur, _isGap:true });
    }
    cur = Math.max(cur, k.end);
  }
  if (cur < root.end){
    gaps.push({ id: root.id + "/gap@" + cur, name:"Unmapped / Reserved",
      start:cur, end:root.end, size:root.end-cur, _isGap:true });
  }
  return gaps;
}

function itemsForNode(node){
  const kids = childrenOf(node.id);
  const gaps = gapsFromChildren(node, kids);
  return [...kids, ...gaps].sort((a,b)=>a.start-b.start);
}

/* Heights */
function computeHeightsToFit(items, minPx, maxPx, budgetPx, gapPx){
  if (!items.length) return { heights: [], total: 0 };

  const isGap = items.map(it => !!it._isGap);
  const gapCount = isGap.filter(Boolean).length;
  const fixedGap = gapCount * gapPx;
  const nonGapBudget = Math.max(0, budgetPx - fixedGap);

  const sizes = items.map(it => (it._isGap ? 0 : Math.max(it.size, 1)));
  const sumSize = sizes.reduce((a,b)=>a+b, 0) || 1;

  let heights = items.map((it, i) => {
    if (isGap[i]) return gapPx;
    return Math.floor((sizes[i] / sumSize) * nonGapBudget);
  });

  heights = heights.map((h, i) => {
    if (isGap[i]) return h;
    return Math.max(minPx, Math.min(maxPx, h));
  });

  const totalH = () => heights.reduce((a,b)=>a+b, 0);
  let delta = budgetPx - totalH();

  const growable = () => heights.map((h,i)=> (!isGap[i] && h < maxPx) ? i : -1).filter(i=>i>=0);
  const shrinkable = () => heights.map((h,i)=> (!isGap[i] && h > minPx) ? i : -1).filter(i=>i>=0);

  let guard = 0;
  while (delta !== 0 && guard < 2000){
    guard++;
    if (delta > 0){
      const g = growable(); if (!g.length) break;
      const step = Math.max(1, Math.floor(delta / g.length));
      for (const i of g){
        const add = Math.min(step, maxPx - heights[i], delta);
        heights[i] += add; delta -= add;
        if (delta === 0) break;
      }
    } else {
      const s = shrinkable(); if (!s.length) break;
      const need = -delta;
      const step = Math.max(1, Math.floor(need / s.length));
      for (const i of s){
        const sub = Math.min(step, heights[i] - minPx, need);
        heights[i] -= sub; delta += sub;
        if (delta === 0) break;
      }
    }
  }

  return { heights, total: totalH() };
}

function computeCompactHeights(items, minPx, gapPx){
  const heights = items.map(it => it._isGap ? gapPx : minPx);
  const total = heights.reduce((a,b)=>a+b, 0);
  return { heights, total };
}

/* UI helpers */
function addOuterSizeMarker(containerEl, size){
  const mr = document.createElement("div");
  mr.className = "markerR";
  mr.innerHTML = `<span class="sizeTag">${fmtSize(size)}</span>`;
  containerEl.appendChild(mr);
}
function addInnerSizePill(containerEl, size){
  const sp = document.createElement("div");
  sp.className = "sizeIn";
  sp.textContent = fmtSize(size);
  containerEl.appendChild(sp);
}
function setBlockSizeVisible(blockEl, visible){
  const mr = blockEl.querySelector(":scope > .markerR");
  if (mr) mr.style.display = visible ? "" : "none";
  const si = blockEl.querySelector(":scope > .sizeIn");
  if (si) si.style.display = visible ? "" : "none";
}
function depthClass(depth){ return "depth-" + Math.min(4, Math.max(0, depth)); }

/* Marker background for gaps: borrow nearest non-gap sibling */
function markerBgForSlice(slices, idx, fallbackBg){
  const s = slices[idx];
  if (!s) return fallbackBg;

  if (!s.classList.contains("gap")){
    return getComputedStyle(s).backgroundColor;
  }
  for (let j = idx + 1; j < slices.length; j++){
    if (!slices[j].classList.contains("gap")){
      return getComputedStyle(slices[j]).backgroundColor;
    }
  }
  for (let j = idx - 1; j >= 0; j--){
    if (!slices[j].classList.contains("gap")){
      return getComputedStyle(slices[j]).backgroundColor;
    }
  }
  return fallbackBg;
}

/* Precise local Y conversion */
function localY(targetEl, childRectTop){
  const t = targetEl.getBoundingClientRect();
  return (childRectTop - t.top - targetEl.clientTop);
}
function localYBottom(targetEl, childRectBottom, childEl){
  const t = targetEl.getBoundingClientRect();
  const bw = parseFloat(getComputedStyle(childEl).borderBottomWidth || "0") || 0;
  return (childRectBottom - t.top - targetEl.clientTop) - (bw / 2);
}

/* Address markers (outer) */
function renderOuterBoundaryLayer(stackEl, items){
  const old = stackEl.querySelector(":scope > .markerLayerOuter");
  if (old) old.remove();

  const slices = Array.from(stackEl.querySelectorAll(":scope > .slice"));
  if (!slices.length) return;

  const fallbackBg = getComputedStyle(stackEl).backgroundColor;

  const layer = document.createElement("div");
  layer.className = "markerLayerOuter";

  const boundaries = [];
  for (let i = 0; i < slices.length; i++){
    const r = slices[i].getBoundingClientRect();
    boundaries.push({
      y: localY(stackEl, r.top),
      addr: items[i].start,
      bg: markerBgForSlice(slices, i, fallbackBg),
    });
  }
  {
    const last = slices[slices.length - 1];
    const r = last.getBoundingClientRect();
    boundaries.push({
      y: localYBottom(stackEl, r.bottom, last),
      addr: items[items.length - 1].end,
      bg: markerBgForSlice(slices, slices.length - 1, fallbackBg),
    });
  }

  const byY = new Map();
  for (const b of boundaries){
    const key = yKey(b.y);
    if (!byY.has(key)) byY.set(key, b);
  }

  const uniq = Array.from(byY.values()).sort((a,b)=>a.y-b.y);

  for (const b of uniq){
    const el = document.createElement("div");
    el.className = "boundaryOuter";
    el.style.top = Math.round(b.y) + "px";
    el.innerHTML =
      `<span class="markerPill" style="background:${b.bg};">${hex(b.addr)}</span>` +
      `<span class="tick"></span>`;
    layer.appendChild(el);
  }

  stackEl.appendChild(layer);
}

/* Address markers (inner lane) */
function renderInnerLaneMarkers(innerLaneEl, innerStackEl, items){
  innerLaneEl.innerHTML = "";
  innerLaneEl.className = "innerLane";

  const slices = Array.from(innerStackEl.querySelectorAll(":scope > .innerSlice"));
  if (!slices.length) return;

  const parentBlock = innerStackEl.closest(".slice, .innerSlice");
  const fallbackBg = parentBlock
    ? getComputedStyle(parentBlock).backgroundColor
    : getComputedStyle(innerStackEl).backgroundColor;

  const boundaries = [];
  for (let i = 0; i < slices.length; i++){
    const r = slices[i].getBoundingClientRect();
    boundaries.push({
      y: localY(innerStackEl, r.top),
      addr: items[i].start,
      bg: markerBgForSlice(slices, i, fallbackBg),
    });
  }
  {
    const last = slices[slices.length - 1];
    const r = last.getBoundingClientRect();
    boundaries.push({
      y: localYBottom(innerStackEl, r.bottom, last),
      addr: items[items.length - 1].end,
      bg: markerBgForSlice(slices, slices.length - 1, fallbackBg),
    });
  }

  const byY = new Map();
  for (const b of boundaries){
    const key = yKey(b.y);
    if (!byY.has(key)) byY.set(key, b);
  }

  const uniq = Array.from(byY.values()).sort((a,b)=>a.y-b.y);

  for (const b of uniq){
    const el = document.createElement("div");
    el.className = "laneBoundary";
    el.style.top = Math.round(b.y) + "px";
    el.innerHTML =
      `<span class="markerPill" style="background:${b.bg};">${hex(b.addr)}</span>` +
      `<span class="tick"></span>`;
    innerLaneEl.appendChild(el);
  }
}

/* Expand/collapse sizing base */
function rememberBaseHeight(blockEl, baseH){
  if (!blockEl.dataset.baseH){
    blockEl.dataset.baseH = String(baseH);
  }
}
function getBaseHeight(blockEl){
  const v = parseFloat(blockEl.dataset.baseH || "0");
  return Number.isFinite(v) && v > 0 ? v : 0;
}

/* ✅ robust content height: last child bottom (works for deep collapse) */
function measureInnerStackContentHeight(innerStack){
  if (!innerStack) return 0;
  const kids = innerStack.querySelectorAll(":scope > .innerSlice");
  if (!kids.length) return 0;
  const last = kids[kids.length - 1];
  return (last.offsetTop + last.offsetHeight);
}

/* Expanded height measurement (FIXED) */
function requiredExpandedHeight(blockEl){
  const base = getBaseHeight(blockEl) || blockEl.offsetHeight;

  const inner = blockEl.querySelector(":scope > .inner");
  if (!inner || inner.style.display === "none") return base;

  const innerStack = inner.querySelector(":scope > .innerShell > .innerStack");
  if (!innerStack) return base;

  // force layout before measuring offsets
  void innerStack.offsetHeight;

  const contentH = measureInnerStackContentHeight(innerStack);
  const needed = contentH + INNER_PAD_Y;

  return Math.max(base, needed);
}

function domDepth(el){
  let d = 0, cur = el;
  while (cur && cur.parentElement){ d++; cur = cur.parentElement; }
  return d;
}

function isActuallyExpanded(blockEl){
  if (blockEl.classList.contains("expanded")) return true;
  const inner = blockEl.querySelector(":scope > .inner");
  if (!inner) return false;
  if (inner.style.display === "none") return false;
  const innerStack = inner.querySelector(":scope > .innerShell > .innerStack");
  return !!innerStack;
}

function listExpandedBlocks(){
  const all = Array.from(document.querySelectorAll(".slice, .innerSlice"));
  const expanded = all.filter(isActuallyExpanded);
  expanded.sort((a,b) => domDepth(b) - domDepth(a)); // deepest first
  return expanded;
}

/* ✅ GLOBAL RELAYOUT: recompute ALL expanded blocks bottom-up until stable */
function relayoutAllExpanded(maxIters = 60){
  const stack = document.getElementById("stack");

  for (let iter = 0; iter < maxIters; iter++){
    const expanded = listExpandedBlocks();
    let changed = false;

    for (const el of expanded){
      const need = Math.round(requiredExpandedHeight(el));
      const curH = Math.round(parseFloat(el.style.height || el.offsetHeight));
      if (Math.abs(curH - need) >= 1){
        el.style.height = need + "px";
        changed = true;
      }
    }

    // layout flush so measurements reflect the new heights
    void stack.offsetHeight;

    if (!changed) break;
  }
}

function afterLayout2(fn){
  requestAnimationFrame(() => requestAnimationFrame(fn));
}
function afterLayout3(fn){
  requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(fn)));
}

function refreshAllMarkers(){
  const stack = document.getElementById("stack");
  const root = byId.get(DATA.root.id);
  renderOuterBoundaryLayer(stack, itemsForNode(root));

  const expandedBlocks = listExpandedBlocks();
  for (const blk of expandedBlocks){
    const nodeId = blk.dataset.nodeId;
    if (!nodeId) continue;
    const node = byId.get(nodeId);
    if (!node) continue;

    const inner = blk.querySelector(":scope > .inner");
    if (!inner || inner.style.display === "none") continue;

    const lane = inner.querySelector(":scope > .innerShell > .innerLane");
    const innerStack = inner.querySelector(":scope > .innerShell > .innerStack");
    if (!lane || !innerStack) continue;

    renderInnerLaneMarkers(lane, innerStack, itemsForNode(node));
  }
}

function renderInner(parentNode, innerContainerEl, level, depth){
  const items = itemsForNode(parentNode);

  innerContainerEl.innerHTML = `
    <div class="innerShell">
      <div class="innerLane"></div>
      <div class="innerStack"></div>
    </div>
  `;
  const innerLaneEl = innerContainerEl.querySelector(".innerLane");
  const innerStackEl = innerContainerEl.querySelector(".innerStack");

  const { heights } = computeCompactHeights(items, MIN_PX_INNER, GAP_PX_INNER);

  items.forEach((it, idx) => {
    const el = document.createElement("div");
    el.className = "innerSlice " + depthClass(depth) + (it._isGap ? " gap" : "");
    el.dataset.nodeId = it._isGap ? "" : it.id;

    const baseH = heights[idx];
    el.style.height = baseH + "px";
    rememberBaseHeight(el, baseH);

    addInnerSizePill(el, it.size);

    const lab = document.createElement("div");
    lab.className = "label";
    lab.innerHTML = `<div class="name">${it.name}</div>`;
    el.appendChild(lab);

    if (it._isGap){
      el.addEventListener("click", (e) => e.stopPropagation());
    }

    if (!it._isGap){
      const drillable = hasChildren(it.id);

      el.addEventListener("click", (e) => {
        e.stopPropagation();
        if (!drillable) return;

        const expanded = el.classList.toggle("expanded");
        if (expanded){
          lab.style.display = "none";
          setBlockSizeVisible(el, false);

          const inner = document.createElement("div");
          inner.className = "inner";
          inner.style.display = "block";
          el.appendChild(inner);

          renderInner(byId.get(it.id), inner, level + 1, depth + 1);

          afterLayout3(() => {
            relayoutAllExpanded();
            refreshAllMarkers();
          });
        } else {
          const inner = el.querySelector(":scope > .inner");
          if (inner) inner.remove();

          lab.style.display = "";
          setBlockSizeVisible(el, true);
          el.style.height = getBaseHeight(el) + "px";

          afterLayout3(() => {
            relayoutAllExpanded();
            refreshAllMarkers();
          });
        }
      });
    }

    innerStackEl.appendChild(el);
  });

  afterLayout2(() => renderInnerLaneMarkers(innerLaneEl, innerStackEl, items));
}

function expandRecursively(blockEl, nodeId, depth){
  const node = byId.get(nodeId);
  if (!node || !hasChildren(nodeId)) return;

  blockEl.dataset.nodeId = nodeId;
  blockEl.classList.add("expanded");

  const lab = blockEl.querySelector(":scope > .label");
  if (lab) lab.style.display = "none";
  setBlockSizeVisible(blockEl, false);

  let inner = blockEl.querySelector(":scope > .inner");
  if (!inner){
    inner = document.createElement("div");
    inner.className = "inner";
    inner.style.display = "block";
    blockEl.appendChild(inner);
  } else {
    inner.style.display = "block";
  }

  renderInner(node, inner, depth + 1, depth + 1);

  afterLayout3(() => {
    const kids = itemsForNode(node).filter(it => !it._isGap);
    const childBlocks = Array.from(inner.querySelectorAll(":scope > .innerShell > .innerStack > .innerSlice"))
      .filter(el => !el.classList.contains("gap"));

    kids.forEach((child, idx) => {
      const childEl = childBlocks[idx];
      if (childEl && hasChildren(child.id)){
        expandRecursively(childEl, child.id, depth + 1);
      }
    });

    afterLayout3(() => {
      relayoutAllExpanded();
      refreshAllMarkers();
    });
  });
}

function collapseTopSliceKeepInner(sliceEl){
  sliceEl.classList.remove("expanded");
  setBlockSizeVisible(sliceEl, true);

  const lab = sliceEl.querySelector(":scope > .label");
  if (lab) lab.style.display = "";

  const inner = sliceEl.querySelector(":scope > .inner");
  if (inner){
    inner.style.display = "none";
    inner.innerHTML = "";
  }

  const base = getBaseHeight(sliceEl);
  if (base) sliceEl.style.height = base + "px";
}

function expandAll(){
  const stack = document.getElementById("stack");
  const root = byId.get(DATA.root.id);
  const items = itemsForNode(root);

  const slices = Array.from(stack.querySelectorAll(":scope > .slice"));
  slices.forEach((slice, idx) => {
    const it = items[idx];
    if (!it || it._isGap) return;
    if (!hasChildren(it.id)) return;
    expandRecursively(slice, it.id, 0);
  });

  afterLayout3(() => {
    relayoutAllExpanded();
    refreshAllMarkers();
  });
}

function collapseAll(){
  const stack = document.getElementById("stack");
  const slices = Array.from(stack.querySelectorAll(":scope > .slice"));
  slices.forEach(s => collapseTopSliceKeepInner(s));
  afterLayout3(() => {
    relayoutAllExpanded();
    refreshAllMarkers();
  });
}

/* Top-level render */
function renderTop(){
  const root = byId.get(DATA.root.id);
  const stack = document.getElementById("stack");
  stack.innerHTML = "";
  stack.style.height = "auto";

  const items = itemsForNode(root);

  const minRequired =
    items.filter(it => it._isGap).length * GAP_PX_OUTER +
    items.filter(it => !it._isGap).length * MIN_PX;

  const wrap = document.querySelector(".wrap");
  const visible = Math.max(320, wrap ? wrap.clientHeight : 900);
  const budget = Math.max(minRequired, visible);

  const HOME_MAX = 140;
  const { heights } = computeHeightsToFit(items, MIN_PX, HOME_MAX, budget, GAP_PX_OUTER);

  items.forEach((it, idx) => {
    const slice = document.createElement("div");
    slice.className = "slice depth-0" + (it._isGap ? " gap" : "");
    slice.dataset.nodeId = it._isGap ? "" : it.id;

    const baseH = heights[idx];
    slice.style.height = baseH + "px";
    rememberBaseHeight(slice, baseH);

    addOuterSizeMarker(slice, it.size);

    const label = document.createElement("div");
    label.className = "label";
    label.innerHTML = `<div class="name">${it.name}</div>`;
    slice.appendChild(label);

    const inner = document.createElement("div");
    inner.className = "inner";
    inner.style.display = "none";
    slice.appendChild(inner);

    if (it._isGap){
      slice.addEventListener("click", (e) => e.stopPropagation());
    }

    if (!it._isGap){
      const drillable = hasChildren(it.id);

      slice.addEventListener("click", (e) => {
        e.stopPropagation();
        if (!drillable) return;

        const expanded = slice.classList.toggle("expanded");
        if (expanded){
          inner.style.display = "block";
          setBlockSizeVisible(slice, false);
          label.style.display = "none";

          renderInner(byId.get(it.id), inner, 1, 1);

          afterLayout3(() => {
            relayoutAllExpanded();
            refreshAllMarkers();
          });
        } else {
          collapseTopSliceKeepInner(slice);
          afterLayout3(() => {
            relayoutAllExpanded();
            refreshAllMarkers();
          });
        }
      });
    }

    stack.appendChild(slice);
  });

  afterLayout3(() => {
    relayoutAllExpanded();
    refreshAllMarkers();
  });
}

/* Buttons */
document.getElementById("collapseAllBtn").addEventListener("click", collapseAll);
document.getElementById("expandAllBtn").addEventListener("click", expandAll);

/* Init */
renderTop();
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description="Convert memory map JSON to interactive HTML")
    ap.add_argument("json_file", help="Input JSON file")
    ap.add_argument("-o", "--out", default="memmap.html", help="Output HTML file")
    args = ap.parse_args()

    with open(args.json_file, "r", encoding="utf-8") as f:
        raw = json.load(f)

    root = build_node(raw)
    errs = validate_tree(root)
    if errs:
        raise SystemExit("Validation failed:\n- " + "\n- ".join(errs))

    flat = flatten(root)
    payload = {
        "root": {
            "id": flat[0]["id"],
            "name": root.name,
            "start": root.start,
            "size": root.size,
            "end": root.end
        },
        "nodes": flat
    }

    html = HTML.replace("__DATA_JSON__", json.dumps(payload))
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Wrote: {args.out}")


if __name__ == "__main__":
    main()
