// Client-only 3D "brain map" of a music library.
// Loaded with next/dynamic (ssr: false) because three.js needs the browser.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ForceGraph3D from "react-force-graph-3d";
import * as THREE from "three";
import { colorFor } from "./colors";

const HIDDEN_COLOR = "#f0abfc";
const PICK_COLOR = "#fde68a";

// One soft glowing dot texture, shared by every node
let glowTexture = null;
function getGlowTexture() {
  if (glowTexture) return glowTexture;
  const size = 128;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d");
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  g.addColorStop(0, "rgba(255,255,255,1)");
  g.addColorStop(0.18, "rgba(255,255,255,0.85)");
  g.addColorStop(0.45, "rgba(255,255,255,0.25)");
  g.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
  glowTexture = new THREE.CanvasTexture(canvas);
  return glowTexture;
}

let ringTexture = null;
function getRingTexture() {
  if (ringTexture) return ringTexture;
  const size = 128;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d");
  ctx.strokeStyle = "rgba(255,255,255,0.9)";
  ctx.lineWidth = 5;
  ctx.shadowColor = "#ffffff";
  ctx.shadowBlur = 12;
  ctx.beginPath();
  ctx.arc(size / 2, size / 2, size / 2 - 12, 0, Math.PI * 2);
  ctx.stroke();
  ringTexture = new THREE.CanvasTexture(canvas);
  return ringTexture;
}

function textSprite(text, color) {
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  const font = "600 44px Inter, system-ui, sans-serif";
  ctx.font = font;
  const w = Math.ceil(ctx.measureText(text).width) + 40;
  canvas.width = w;
  canvas.height = 72;
  ctx.font = font;
  ctx.fillStyle = color;
  ctx.shadowColor = color;
  ctx.shadowBlur = 16;
  ctx.textBaseline = "middle";
  ctx.fillText(text, 20, 36);
  const mat = new THREE.SpriteMaterial({
    map: new THREE.CanvasTexture(canvas), transparent: true, depthWrite: false, depthTest: false,
    opacity: 0.9, sizeAttenuation: false,
  });
  const sprite = new THREE.Sprite(mat);
  // Fixed on-screen size, whatever the zoom
  const h = 0.032;
  sprite.scale.set((h * w) / 72, h, 1);
  return sprite;
}

export default function Graph3D({ data, selectedId, focusIds, focusCluster, picks, mode, onSelect }) {
  const fgRef = useRef();
  const wrapRef = useRef();
  const [size, setSize] = useState({ width: 800, height: 600 });

  // Fit the canvas to its container
  useEffect(() => {
    if (!wrapRef.current) return;
    // Skip 0x0 sizes: the map page is hidden (not unmounted) while you're on another tab
    const ro = new ResizeObserver(([e]) => {
      const { width, height } = e.contentRect;
      if (width && height) setSize({ width, height });
    });
    ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, []);

  const glowMats = useRef(new Map()); // node id -> glow material, so dimming never rebuilds the scene
  const labelSprites = useRef(new Map()); // cluster id -> label sprite

  const graph = useMemo(() => {
    glowMats.current.clear();
    if (!data) return { nodes: [], links: [] };
    // Imports without play counts have no engagement; give every star the same modest size
    const engs = data.tracks.map((t) => t.engagement).filter((v) => v != null);
    const maxEng = engs.length ? Math.max(...engs) : 0;
    return {
      nodes: data.tracks.map((t) => ({
        ...t,
        // Pin each track where the embedding put it, so position means similarity
        fx: t.x, fy: t.y, fz: t.z,
        size: maxEng > 0 ? 2.5 + 5.5 * ((t.engagement ?? 0) / maxEng) : 3.5,
      })),
      links: data.edges.map((e) => ({ ...e })),
    };
  }, [data]);

  const pickSet = useMemo(() => new Set(picks || []), [picks]);
  const focus = focusIds && focusIds.size ? focusIds : null;

  const DIM = 0.22;
  const focusRef = useRef(focus);
  focusRef.current = focus;

  // Glowing sprite per node. Only rebuilt when the selection or mode changes;
  // focus changes just fade materials (see the effect below), which avoids the
  // whole map flickering out and back in when you pick a cluster.
  const nodeObject = useCallback((node) => {
    const group = new THREE.Group();
    const f = focusRef.current;
    const lit = !f || f.has(node.id);
    const isPick = mode === "picks" && pickSet.has(node.id);
    const color = isPick ? PICK_COLOR : colorFor(node.cluster);
    const mat = new THREE.SpriteMaterial({
      map: getGlowTexture(),
      color,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      opacity: lit ? 0.9 : DIM,
    });
    glowMats.current.set(node.id, mat);
    const glow = new THREE.Sprite(mat);
    const s = node.id === selectedId ? node.size * 2.6 : isPick ? Math.max(node.size, 5) * 2 : node.size * 1.6;
    glow.scale.set(s, s, 1);
    group.add(glow);
    if (node.id === selectedId) {
      // A sprite always faces the camera, so the ring stays round from any angle
      const ring = new THREE.Sprite(new THREE.SpriteMaterial({ map: getRingTexture(), transparent: true, depthWrite: false }));
      ring.scale.set(s * 1.1, s * 1.1, 1);
      group.add(ring);
    }
    return group;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, mode, pickSet, data]);

  // Fade tracks and cluster names in and out of focus
  useEffect(() => {
    for (const [id, mat] of glowMats.current) mat.opacity = !focus || focus.has(id) ? 0.9 : DIM;
    const litClusters = focus ? new Set((data?.tracks || []).filter((t) => focus.has(t.id)).map((t) => t.cluster)) : null;
    for (const [cid, sprite] of labelSprites.current) sprite.material.opacity = !litClusters || litClusters.has(cid) ? 0.9 : 0.25;
  }, [focus, data]);

  const linkVisible = (l) => {
    const s = typeof l.source === "object" ? l.source.id : l.source;
    const t = typeof l.target === "object" ? l.target.id : l.target;
    if (selectedId != null) return s === selectedId || t === selectedId;
    if (mode === "hidden") return l.kind === "hidden";
    if (focus) return focus.has(s) && focus.has(t);
    // Overview: keep each cluster's own web plus the hidden threads. Links between
    // neighbouring clusters are left out, or a real library turns into one big mesh.
    return l.kind === "hidden" || !l.bridge;
  };

  // Cluster names floating above each group
  useEffect(() => {
    const fg = fgRef.current;
    if (!fg || !data) return;
    const scene = fg.scene();
    const labels = new THREE.Group();
    labels.name = "cluster-labels";
    for (const c of data.clusters) {
      const members = data.tracks.filter((t) => t.cluster === c.id);
      if (!members.length) continue;
      const cx = members.reduce((a, t) => a + t.x, 0) / members.length;
      const cy = Math.max(...members.map((t) => t.y)) + 6;
      const cz = members.reduce((a, t) => a + t.z, 0) / members.length;
      const name = c.label.split(" · ").slice(0, 2).join(" · ");
      const sprite = textSprite(name, colorFor(c.id));
      sprite.position.set(cx, cy, cz);
      labelSprites.current.set(c.id, sprite);
      labels.add(sprite);
    }
    scene.add(labels);
    return () => {
      scene.remove(labels);
      labelSprites.current.clear();
    };
  }, [data]);

  // Frame the whole map once it loads
  useEffect(() => {
    const fg = fgRef.current;
    if (!fg || !data) return;
    // Pull back far enough for the widest library to fit
    const r = Math.max(90, ...data.tracks.map((t) => Math.hypot(t.x, t.y, t.z)));
    const t = setTimeout(() => fg.cameraPosition({ x: 0, y: r * 0.17, z: r * 1.75 }, { x: 0, y: 0, z: 0 }, 1200), 50);
    return () => clearTimeout(t);
  }, [data]);

  // Fly to a picked cluster, and back out to the whole map when it is cleared
  const framedCluster = useRef(null);
  useEffect(() => {
    const fg = fgRef.current;
    if (!fg || !data || selectedId != null) return;
    if (focusCluster == null) {
      if (framedCluster.current == null) return;
      framedCluster.current = null;
      const r = Math.max(90, ...data.tracks.map((t) => Math.hypot(t.x, t.y, t.z)));
      fg.cameraPosition({ x: 0, y: r * 0.17, z: r * 1.75 }, { x: 0, y: 0, z: 0 }, 1000);
      return;
    }
    const members = data.tracks.filter((t) => t.cluster === focusCluster);
    if (!members.length) return;
    framedCluster.current = focusCluster;
    const c = ["x", "y", "z"].map((k) => members.reduce((a, t) => a + t[k], 0) / members.length);
    const spread = Math.max(20, ...members.map((t) => Math.hypot(t.x - c[0], t.y - c[1], t.z - c[2])));
    fg.cameraPosition({ x: c[0], y: c[1] + spread * 0.3, z: c[2] + spread * 3 }, { x: c[0], y: c[1], z: c[2] }, 1000);
  }, [focusCluster, selectedId, data]);

  // Fly to the selected track
  useEffect(() => {
    const fg = fgRef.current;
    if (!fg || selectedId == null || !data) return;
    const n = data.tracks.find((t) => t.id === selectedId);
    if (!n) return;
    const dist = 70;
    const r = Math.hypot(n.x, n.y, n.z) || 1;
    const k = 1 + dist / r;
    fg.cameraPosition({ x: n.x * k, y: n.y * k, z: n.z * k }, { x: n.x, y: n.y, z: n.z }, 1000);
  }, [selectedId, data]);

  return (
    <div ref={wrapRef} className="absolute inset-0">
      <ForceGraph3D
        ref={fgRef}
        width={size.width}
        height={size.height}
        graphData={graph}
        backgroundColor="rgba(0,0,0,0)"
        showNavInfo={false}
        cooldownTicks={0}
        warmupTicks={0}
        enableNodeDrag={false}
        nodeThreeObject={nodeObject}
        nodeLabel={(n) =>
          `<div style="font:12px Inter,system-ui;padding:6px 8px;background:#0b1121ee;border:1px solid #ffffff22;border-radius:8px;color:#e5e7eb">
             <b>${n.title}</b>${n.artist ? ` · ${n.artist}` : ""}<br/>
             <span style="color:#9ca3af">${[n.genre, n.key && `${n.key} (${n.camelot})`, n.bpm && `${Math.round(n.bpm)} BPM`, n.plays != null && `${n.plays} plays`].filter(Boolean).join(" · ")}</span>
           </div>`
        }
        onNodeClick={(n) => onSelect?.(n.id)}
        onBackgroundClick={() => onSelect?.(null)}
        linkVisibility={linkVisible}
        linkColor={(l) => (l.kind === "hidden" ? HIDDEN_COLOR : colorFor(typeof l.source === "object" ? l.source.cluster : 0))}
        linkOpacity={0.22}
        linkWidth={(l) => (l.kind === "hidden" ? 0.6 : 0.25)}
        linkDirectionalParticles={(l) => (l.kind === "hidden" ? 2 : focus ? 1 : 0)}
        linkDirectionalParticleWidth={(l) => (l.kind === "hidden" ? 1.2 : 1)}
        linkDirectionalParticleSpeed={(l) => 0.004 + 0.006 * (l.strength ?? 0.5)}
        linkDirectionalParticleColor={(l) => (l.kind === "hidden" ? HIDDEN_COLOR : "#ffffff")}
      />
    </div>
  );
}
