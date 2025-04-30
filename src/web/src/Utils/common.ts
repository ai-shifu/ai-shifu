const MODAL_DEFAULT_WIDTH = '360px';

// calculate modal width
export const calModalWidth = ({ inMobile, width = MODAL_DEFAULT_WIDTH }) => {
  return inMobile ? '100%' : width;
};

// generate uuid
export const genUuid = () => {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
    var r = (Math.random() * 16) | 0,
      v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
};
