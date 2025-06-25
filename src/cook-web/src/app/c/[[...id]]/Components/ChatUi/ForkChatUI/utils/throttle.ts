export default function throttle(fn: (...args: any[]) => unknown, delay = 300) {
  let ready = true;

  return (...args: any) => {
    if (!ready) {
      return;
    }

    ready = false;
    fn(...args);

    setTimeout(() => {
      ready = true;
    }, delay);
  };
}
