// Leaf-vein background dynamic canvas animation
(function () {
  const c = document.getElementById('veins');
  if (!c) return;
  const x = c.getContext('2d');
  let W, H, tips = [], last = 0;
  const calm = matchMedia('(prefers-reduced-motion:reduce)').matches;

  function size() {
    const d = devicePixelRatio || 1;
    W = innerWidth;
    H = innerHeight;
    c.width = W * d;
    c.height = H * d;
    x.setTransform(d, 0, 0, d, 0, 0);
  }

  size();
  addEventListener('resize', size);

  function col(a) {
    const veinsColor = getComputedStyle(document.documentElement).getPropertyValue('--veins').trim();
    return `rgba(${veinsColor},${a})`;
  }

  function spawn(px, py, n) {
    for (let i = 0; i < n; i++) {
      tips.push({
        x: px,
        y: py,
        a: Math.random() * 6.28,
        l: 30 + Math.random() * 50,
        w: 1.6,
        d: 0,
      });
    }
  }

  addEventListener('pointermove', (e) => {
    const t = performance.now();
    if (t - last < 90 || calm) return;
    last = t;
    spawn(e.clientX, e.clientY, 1);
  });

  addEventListener('pointerdown', (e) => {
    if (!calm) spawn(e.clientX, e.clientY, 6);
  });

  if (!calm) {
    setInterval(() => spawn(Math.random() * W, Math.random() * H, 1), 1800);
  }

  function frame() {
    x.globalCompositeOperation = 'destination-out';
    x.fillStyle = 'rgba(0,0,0,.012)';
    x.fillRect(0, 0, W, H);
    x.globalCompositeOperation = 'source-over';
    x.strokeStyle = col(0.5);
    const next = [];

    for (const t of tips) {
      const nx = t.x + Math.cos(t.a) * 2.2;
      const ny = t.y + Math.sin(t.a) * 2.2;
      x.lineWidth = t.w;
      x.beginPath();
      x.moveTo(t.x, t.y);
      x.lineTo(nx, ny);
      x.stroke();
      t.x = nx;
      t.y = ny;
      t.a += (Math.random() - 0.5) * 0.25;
      t.l--;
      t.w *= 0.994;
      if (t.l > 0) next.push(t);
      if (t.d < 3 && Math.random() < 0.025 && tips.length < 220) {
        next.push({
          x: t.x,
          y: t.y,
          a: t.a + (Math.random() < 0.5 ? -0.7 : 0.7),
          l: t.l * 0.7,
          w: t.w * 0.7,
          d: t.d + 1,
        });
      }
    }
    tips = next;
    requestAnimationFrame(frame);
  }

  if (!calm) frame();
})();
