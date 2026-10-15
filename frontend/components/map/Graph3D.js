// Client-only 3D "brain map" of a music library.
// Loaded with next/dynamic (ssr: false) because three.js needs the browser.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ForceGraph3D from "react-force-graph-3d";
import * as THREE from "three";
import { colorFor } from "./colors";

const HIDDEN_COLOR = "#f0abfc";
const PICK_COLOR = "#fde68a";

// Above this many songs, stars are drawn as one point cloud and links as one set of
// line segments (two draw calls) instead of one three.js object each. A sprite per song
// is fine for a few thousand but crawls at 20,000.
export const LARGE_MAP = 2500;

const libraryRadius = (tracks) => tracks.reduce((r, t) => Math.max(r, Math.hypot(t.x, t.y, t.z)), 90);

// Point cloud shader: each point is the same soft glow as a sprite, sized in world
// units (so it shrinks with distance) and with its own colour and opacity.
const POINT_VERTEX = `
  attribute float size;
  attribute vec3 starColor;
  attribute float alpha;
  uniform float uScale;
  varying vec3 vColor;
  varying float vAlpha;
  void main() {
    vColor = starColor;
    vAlpha = alpha;
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    gl_PointSize = clamp(size * uScale / -mv.z, 2.5, 48.0);
    gl_Position = projectionMatrix * mv;
  }`;
const POINT_FRAGMENT = `
  uniform sampler2D map;
  varying vec3 vColor;
  varying float vAlpha;
  void main() {
    gl_FragColor = vec4(vColor, vAlpha) * texture2D(map, gl_PointCoord);
  }`;

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

export default function Graph3D({ data, selectedId, focusIds, focusCluster, picks, mode, onSelect, colorOf }) {
  const fgRef = useRef();
  const wrapRef = useRef();
  const [size, setSize] = useState({ width: 800, height: 600 });
  const large = (data?.tracks?.length || 0) > LARGE_MAP;
  const colorOfTrack = colorOf || ((t) => colorFor(t.cluster));

  // Fit the canvas to its container
  useEffect(() => {
    if (!wrapRef.current) return;
    // Skip 0x0 sizes: the map page is hidden (not unmounted) while you're on another tab
    const ro = new ResizeObserver(([e]) => {
      const { width, height } = e.contentRect;
      if (!width || !height) return;
      setSize({ width, height });
      // The rotate controls measure the canvas once; if the map was built while hidden
      // they measured 0x0 and dragging does nothing, so let them measure again
      fgRef.current?.controls()?.handleResize?.();
    });
    ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, []);

  const glowMats = useRef(new Map()); // node id -> glow material, so dimming never rebuilds the scene
  const labelSprites = useRef(new Map()); // cluster id -> label sprite

  // Imports without play counts have no engagement; give every star the same modest size
  const sizes = useMemo(() => {
    if (!data) return [];
    const maxEng = data.tracks.reduce((m, t) => Math.max(m, t.engagement ?? 0), 0);
    return data.tracks.map((t) => (maxEng > 0 ? 2.5 + 5.5 * ((t.engagement ?? 0) / maxEng) : 3.5));
  }, [data]);

  const graph = useMemo(() => {
    glowMats.current.clear();
    if (!data || large) return { nodes: [], links: [] };
    return {
      nodes: data.tracks.map((t, i) => ({
        ...t,
        // Pin each track where the embedding put it, so position means similarity
        fx: t.x, fy: t.y, fz: t.z,
        size: sizes[i],
      })),
      links: data.edges.map((e) => ({ ...e })),
    };
  }, [data, large, sizes]);

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
    const color = isPick ? PICK_COLOR : colorOfTrack(node);
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
  }, [selectedId, mode, pickSet, data, colorOf]);

  // Fade tracks and cluster names in and out of focus
  useEffect(() => {
    for (const [id, mat] of glowMats.current) mat.opacity = !focus || focus.has(id) ? 0.9 : DIM;
    const litClusters = focus ? new Set((data?.tracks || []).filter((t) => focus.has(t.id)).map((t) => t.cluster)) : null;
    for (const [cid, sprite] of labelSprites.current) sprite.material.opacity = !litClusters || litClusters.has(cid) ? 0.9 : 0.25;
  }, [focus, data]);

  const linkVisible = (l) => {
    if (large) return false; // drawn by the point-cloud view below
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
    // Big libraries have 20+ clusters; naming them all buries the map, so name the 12 biggest
    const named = new Set([...data.clusters].sort((a, b) => b.size - a.size).slice(0, 12).map((c) => c.id));
    for (const c of data.clusters) {
      if (!named.has(c.id)) continue;
      const members = data.tracks.filter((t) => t.cluster === c.id);
      if (!members.length) continue;
      const cx = members.reduce((a, t) => a + t.x, 0) / members.length;
      const cy = members.reduce((m, t) => Math.max(m, t.y), -Infinity) + 6;
      const cz = members.reduce((a, t) => a + t.z, 0) / members.length;
      const name = c.name ? `${c.name} · ${c.label.split(" · ")[0]}` : c.label.split(" · ").slice(0, 2).join(" · ");
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
    const r = libraryRadius(data.tracks);
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
      const r = libraryRadius(data.tracks);
      fg.cameraPosition({ x: 0, y: r * 0.17, z: r * 1.75 }, { x: 0, y: 0, z: 0 }, 1000);
      return;
    }
    const members = data.tracks.filter((t) => t.cluster === focusCluster);
    if (!members.length) return;
    framedCluster.current = focusCluster;
    const c = ["x", "y", "z"].map((k) => members.reduce((a, t) => a + t[k], 0) / members.length);
    const spread = members.reduce((m, t) => Math.max(m, Math.hypot(t.x - c[0], t.y - c[1], t.z - c[2])), 20);
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

  // ---- Large maps: one point cloud for the stars, one set of line segments for links ----
  const cloud = useRef(null); // { points, lines, ring, geometry }
  useEffect(() => {
    const fg = fgRef.current;
    if (!fg || !data || !large) return;
    const n = data.tracks.length;
    const geometry = new THREE.BufferGeometry();
    const pos = new Float32Array(n * 3);
    data.tracks.forEach((t, i) => { pos[i * 3] = t.x; pos[i * 3 + 1] = t.y; pos[i * 3 + 2] = t.z; });
    geometry.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geometry.setAttribute("starColor", new THREE.BufferAttribute(new Float32Array(n * 3), 3));
    geometry.setAttribute("alpha", new THREE.BufferAttribute(new Float32Array(n), 1));
    geometry.setAttribute("size", new THREE.BufferAttribute(new Float32Array(n), 1));
    const material = new THREE.ShaderMaterial({
      uniforms: { map: { value: getGlowTexture() }, uScale: { value: 600 } },
      vertexShader: POINT_VERTEX, fragmentShader: POINT_FRAGMENT,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    });
    const points = new THREE.Points(geometry, material);
    points.frustumCulled = false;
    const lines = new THREE.LineSegments(
      new THREE.BufferGeometry(),
      new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.3, depthWrite: false, blending: THREE.AdditiveBlending }),
    );
    lines.frustumCulled = false;
    const ring = new THREE.Sprite(new THREE.SpriteMaterial({ map: getRingTexture(), transparent: true, depthWrite: false }));
    ring.visible = false;
    // A soft nebula behind each cluster, so 20,000 stars read as islands, not one fog
    const nebulae = new THREE.Group();
    const byCluster = new Map();
    for (const t of data.tracks) {
      const a = byCluster.get(t.cluster) || [];
      a.push(t);
      byCluster.set(t.cluster, a);
    }
    for (const [cid, ts] of byCluster) {
      if (ts.length < 20) continue;
      const c = ["x", "y", "z"].map((k) => ts.reduce((a, t) => a + t[k], 0) / ts.length);
      const r = ts.reduce((a, t) => a + Math.hypot(t.x - c[0], t.y - c[1], t.z - c[2]), 0) / ts.length;
      const neb = new THREE.Sprite(new THREE.SpriteMaterial({
        map: getGlowTexture(), color: colorFor(cid), transparent: true, depthWrite: false,
        blending: THREE.AdditiveBlending, opacity: 0.16,
      }));
      neb.position.set(c[0], c[1], c[2]);
      neb.scale.set(r * 4.5, r * 4.5, 1);
      neb.userData.cluster = cid;
      nebulae.add(neb);
    }
    const scene = fg.scene();
    scene.add(nebulae, points, lines, ring);
    cloud.current = { points, lines, ring, geometry, nebulae };
    return () => {
      scene.remove(nebulae, points, lines, ring);
      nebulae.children.forEach((n) => n.material.dispose());
      geometry.dispose(); material.dispose(); lines.geometry.dispose(); lines.material.dispose();
      cloud.current = null;
    };
  }, [data, large]);

  // Star sizes in world units -> pixels, the same maths three.js uses for sprites
  useEffect(() => {
    const fg = fgRef.current;
    if (!large || !cloud.current || !fg) return;
    const cam = fg.camera();
    const dpr = fg.renderer()?.getPixelRatio?.() || 1;
    cloud.current.points.material.uniforms.uScale.value = (size.height * dpr) / (2 * Math.tan((cam.fov * Math.PI) / 360));
  }, [large, size, data]);

  // Colours, focus dimming, picks and the selected star
  useEffect(() => {
    const c = cloud.current;
    if (!large || !c || !data) return;
    const col = c.geometry.getAttribute("starColor");
    const alpha = c.geometry.getAttribute("alpha");
    const sz = c.geometry.getAttribute("size");
    const tmp = new THREE.Color();
    data.tracks.forEach((t, i) => {
      const isPick = mode === "picks" && pickSet.has(t.id);
      tmp.set(isPick ? PICK_COLOR : colorOfTrack(t));
      col.setXYZ(i, tmp.r, tmp.g, tmp.b);
      alpha.setX(i, !focus || focus.has(t.id) ? 0.9 : DIM * 0.6);
      const s = sizes[i];
      sz.setX(i, t.id === selectedId ? s * 2.6 : isPick ? Math.max(s, 5) * 2 : s * 1.6);
    });
    col.needsUpdate = alpha.needsUpdate = sz.needsUpdate = true;
    const litClusters = focus ? new Set(data.tracks.filter((t) => focus.has(t.id)).map((t) => t.cluster)) : null;
    for (const neb of c.nebulae.children) {
      neb.material.opacity = !litClusters ? 0.16 : litClusters.has(neb.userData.cluster) ? 0.22 : 0.04;
    }
    const sel = selectedId != null ? data.tracks[selectedId] : null;
    c.ring.visible = !!sel;
    if (sel) {
      const s = sizes[selectedId] * 2.6 * 1.1;
      c.ring.position.set(sel.x, sel.y, sel.z);
      c.ring.scale.set(s, s, 1);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [large, data, colorOf, focus, selectedId, mode, pickSet, sizes]);

  // Links: the same rules as the small map, minus the animated particles
  useEffect(() => {
    const c = cloud.current;
    if (!large || !c || !data) return;
    const visible = data.edges.filter((l) => {
      if (selectedId != null) return l.source === selectedId || l.target === selectedId;
      if (mode === "hidden") return l.kind === "hidden";
      if (focus) return focus.has(l.source) && focus.has(l.target);
      return l.kind === "hidden" || !l.bridge;
    });
    const pos = new Float32Array(visible.length * 6);
    const col = new Float32Array(visible.length * 6);
    const tmp = new THREE.Color();
    visible.forEach((l, k) => {
      const a = data.tracks[l.source], b = data.tracks[l.target];
      pos.set([a.x, a.y, a.z, b.x, b.y, b.z], k * 6);
      tmp.set(l.kind === "hidden" ? HIDDEN_COLOR : colorOfTrack(a));
      col.set([tmp.r, tmp.g, tmp.b, tmp.r, tmp.g, tmp.b], k * 6);
    });
    c.lines.geometry.dispose();
    c.lines.geometry = new THREE.BufferGeometry();
    c.lines.geometry.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    c.lines.geometry.setAttribute("color", new THREE.BufferAttribute(col, 3));
    // The overview shows tens of thousands of links: keep them a faint haze
    // A focused cluster of a thousand songs is a hairball at full strength; fade by link count
    c.lines.material.opacity = selectedId != null ? 0.5 : focus ? Math.min(0.4, Math.max(0.06, 60 / Math.sqrt(visible.length + 1) / 10)) : 0.06;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [large, data, selectedId, mode, focus, colorOf]);

  // Hit-testing for the point cloud: the nearest star on screen within a few pixels
  const [hover, setHover] = useState(null); // { t, x, y }
  const nearest = useCallback((clientX, clientY) => {
    const fg = fgRef.current;
    if (!fg || !data) return null;
    const rect = fg.renderer().domElement.getBoundingClientRect();
    const mx = clientX - rect.left, my = clientY - rect.top;
    const cam = fg.camera();
    cam.updateMatrixWorld();
    const m = new THREE.Matrix4().multiplyMatrices(cam.projectionMatrix, cam.matrixWorldInverse).elements;
    let best = null, bestD = 100; // 10 px, squared
    const focus = focusRef.current;
    for (const t of data.tracks) {
      const w = m[3] * t.x + m[7] * t.y + m[11] * t.z + m[15];
      if (w <= 0) continue; // behind the camera
      const sx = ((m[0] * t.x + m[4] * t.y + m[8] * t.z + m[12]) / w + 1) * 0.5 * rect.width;
      const sy = (1 - (m[1] * t.x + m[5] * t.y + m[9] * t.z + m[13]) / w) * 0.5 * rect.height;
      // Dimmed stars only count when nothing lit is close
      const d = (sx - mx) ** 2 + (sy - my) ** 2 + (focus && !focus.has(t.id) ? 30 : 0);
      if (d < bestD) { bestD = d; best = t; }
    }
    return best ? { t: best, x: mx, y: my } : null;
  }, [data]);

  const hoverFrame = useRef(0);
  const onMove = (e) => {
    if (!large || e.buttons) return; // not while orbiting
    const { clientX, clientY } = e;
    cancelAnimationFrame(hoverFrame.current);
    hoverFrame.current = requestAnimationFrame(() => setHover(nearest(clientX, clientY)));
  };

  return (
    <div ref={wrapRef} className="absolute inset-0" onPointerMove={onMove} onPointerLeave={() => setHover(null)}
      style={large && hover ? { cursor: "pointer" } : undefined}>
      {large && hover && (
        <div className="pointer-events-none absolute z-10 rounded-lg border border-white/15 bg-[#0b1121ee] px-2 py-1.5 text-xs text-gray-200"
          style={{ left: Math.min(hover.x + 14, size.width - 240), top: hover.y + 14, maxWidth: 260 }}>
          <b className="text-white">{hover.t.title}</b>{hover.t.artist ? ` · ${hover.t.artist}` : ""}
          <div className="text-gray-400">
            {[hover.t.genre, hover.t.key && `${hover.t.key} (${hover.t.camelot})`, hover.t.bpm && `${Math.round(hover.t.bpm)} BPM`,
              hover.t.plays != null && `${hover.t.plays} plays`].filter(Boolean).join(" · ")}
          </div>
        </div>
      )}
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
        onBackgroundClick={(e) => onSelect?.(large && e ? nearest(e.clientX, e.clientY)?.t.id ?? null : null)}
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
