const polyfillHasOwn = () => {
  if (!Object.hasOwn) {
    Object.hasOwn = function (obj, prop) {
      return Object.prototype.hasOwnProperty.call(obj, prop);
    };
  }
};

const polyfillAll = () => {
  polyfillHasOwn();
};

polyfillAll();
