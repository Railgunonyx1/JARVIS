/**
 * JARVIS MK-X — Canvas Arc Reactor
 * GPU-accelerated 2D canvas renderer with performance-aware animation.
 */

const CIRC = 2 * Math.PI * 42;
let canvas, ctx;
let animFrame = null;
let mode = "balanced"; // eco | balanced | performance
let rotation = 0;
let lastTime = 0;
let cpuUsage = 0;

const FPS = { eco: 12, balanced: 30, performance: 60 };

export function initReactor(canvasEl) {
  canvas = canvasEl;
  ctx = canvas.getContext("2d");
  // High-DPI support
  const dpr = window.devicePixelRatio || 1;
  const w = 300, h = 300;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  ctx.scale(dpr, dpr);
  lastTime = performance.now();
  animFrame = requestAnimationFrame(tick);
}

export function setReactorMode(m) {
  mode = m;
}

export function setReactorCpu(val) {
  cpuUsage = val;
}

export function destroyReactor() {
  if (animFrame) cancelAnimationFrame(animFrame);
}

export function pauseReactor() {
  if (animFrame) { cancelAnimationFrame(animFrame); animFrame = null; }
}

export function resumeReactor() {
  if (!animFrame) { lastTime = performance.now(); animFrame = requestAnimationFrame(tick); }
}

function tick(now) {
  animFrame = requestAnimationFrame(tick);

  const targetInterval = 1000 / FPS[mode];
  const elapsed = now - lastTime;
  if (elapsed < targetInterval * 0.9) return;
  lastTime = now;

  const speed = mode === "eco" ? 0.3 : mode === "performance" ? 1.0 : 0.6;
  rotation += speed * 0.02;

  draw(rotation);
}

function draw(rot) {
  const w = 300, h = 300;
  const cx = w / 2, cy = h / 2;
  ctx.clearRect(0, 0, w, h);

  // Outer ring
  ctx.strokeStyle = "rgba(0,212,255,0.08)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.arc(cx, cy, 140, 0, Math.PI * 2);
  ctx.stroke();

  ctx.strokeStyle = "rgba(0,212,255,0.12)";
  ctx.lineWidth = 0.5;
  ctx.beginPath();
  ctx.arc(cx, cy, 130, 0, Math.PI * 2);
  ctx.stroke();

  // Spinning outer ring
  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(rot);
  ctx.strokeStyle = "rgba(0,212,255,0.25)";
  ctx.lineWidth = 2;
  ctx.setLineDash([15, 10, 5, 10]);
  ctx.beginPath();
  ctx.arc(0, 0, 120, 0, Math.PI * 2);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.restore();

  // Spinning inner ring (reverse)
  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(-rot * 1.5);
  ctx.strokeStyle = "rgba(0,212,255,0.2)";
  ctx.lineWidth = 1.5;
  ctx.setLineDash([20, 8, 8, 8]);
  ctx.beginPath();
  ctx.arc(0, 0, 95, 0, Math.PI * 2);
  ctx.stroke();
  ctx.strokeStyle = "rgba(0,212,255,0.1)";
  ctx.lineWidth = 0.8;
  ctx.setLineDash([8, 15]);
  ctx.beginPath();
  ctx.arc(0, 0, 88, 0, Math.PI * 2);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.restore();

  // Middle ring
  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(rot * 0.7);
  ctx.strokeStyle = "rgba(0,212,255,0.18)";
  ctx.lineWidth = 1;
  ctx.setLineDash([12, 6, 4, 6]);
  ctx.beginPath();
  ctx.arc(0, 0, 70, 0, Math.PI * 2);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.restore();

  // Radial lines
  ctx.strokeStyle = "rgba(0,212,255,0.15)";
  ctx.lineWidth = 0.5;
  const lines = [
    [150, 10, 150, 60], [150, 240, 150, 290],
    [10, 150, 60, 150], [240, 150, 290, 150],
    [48, 48, 83, 83], [217, 217, 252, 252],
    [252, 48, 217, 83], [48, 252, 83, 217],
  ];
  for (const [x1, y1, x2, y2] of lines) {
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
  }

  // Segments
  ctx.fillStyle = "rgba(0,212,255,0.12)";
  ctx.beginPath(); ctx.moveTo(150, 55); ctx.lineTo(165, 85); ctx.lineTo(150, 75); ctx.fill();
  ctx.beginPath(); ctx.moveTo(150, 245); ctx.lineTo(135, 215); ctx.lineTo(150, 225); ctx.fill();
  ctx.beginPath(); ctx.moveTo(55, 150); ctx.lineTo(85, 135); ctx.lineTo(75, 150); ctx.fill();
  ctx.beginPath(); ctx.moveTo(245, 150); ctx.lineTo(215, 165); ctx.lineTo(225, 150); ctx.fill();

  // Core glow - intensity based on CPU
  const glowIntensity = 0.2 + (cpuUsage / 100) * 0.5;
  const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, 45);
  grad.addColorStop(0, `rgba(0,212,255,${glowIntensity})`);
  grad.addColorStop(1, "rgba(0,212,255,0)");
  ctx.fillStyle = grad;
  ctx.beginPath();
  ctx.arc(cx, cy, 45, 0, Math.PI * 2);
  ctx.fill();

  const grad2 = ctx.createRadialGradient(cx, cy, 0, cx, cy, 30);
  grad2.addColorStop(0, `rgba(0,212,255,${glowIntensity + 0.2})`);
  grad2.addColorStop(1, "rgba(0,212,255,0.1)");
  ctx.fillStyle = grad2;
  ctx.beginPath();
  ctx.arc(cx, cy, 30, 0, Math.PI * 2);
  ctx.fill();

  // Inner circle
  ctx.fillStyle = "rgba(0,212,255,0.3)";
  ctx.beginPath();
  ctx.arc(cx, cy, 15, 0, Math.PI * 2);
  ctx.fill();

  // Core point
  ctx.fillStyle = "rgba(255,255,255,0.8)";
  ctx.beginPath();
  ctx.arc(cx, cy, 5, 0, Math.PI * 2);
  ctx.fill();
}
