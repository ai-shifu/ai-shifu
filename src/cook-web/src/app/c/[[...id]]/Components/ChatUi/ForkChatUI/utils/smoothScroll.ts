const rAF = requestAnimationFrame;

interface Props {
  el: HTMLElement;
  to: number;
  duration?: number;
  x?: boolean;
}

export default function smoothScroll({ el, to, duration = 300, x }: Props) {
  let count = 0;
  const attr = x ? 'scrollLeft' : 'scrollTop';
  const from = el[attr];
  const frames = Math.round(duration / 16);
  const step = (to - from) / frames;

  if (!rAF) {
    el[attr] = to;
    return;
  }

  function animate() {
    el[attr] += step;

    if (++count < frames) {
      rAF(animate);
    }
  }

  animate();
}
