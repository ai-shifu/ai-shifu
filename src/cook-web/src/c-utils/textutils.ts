import { isMobile } from "react-device-detect";
import { inWechat } from '@/c-constants/uiConstants';

const isSafari = navigator.userAgent.match(/iPad|iPhone|iPod|Macintosh/i);

const copyTextOld = async (text) => {
  return new Promise((resolve) => {
    const textArea = document.createElement("textArea");
    textArea.value = text;
    textArea.style.width = 0;
    textArea.style.position = "fixed";
    textArea.style.left = "-999px";
    textArea.style.top = "10px";
    textArea.setAttribute("readonly", "readonly");
    document.body.appendChild(textArea);

    textArea.select();
    document.execCommand("copy");
    document.body.removeChild(textArea);
  });
};

const copyTextNew = async (text) => {
  return navigator.clipboard.writeText(text);
};

export const copyText = async (text) => {
  if (isMobile) {
    if (inWechat()) {
      if (navigator.clipboard && isSafari) {
        return copyTextNew(text);
      } else {
        return copyTextOld(text);
      }
    } else {
      if (navigator.clipboard && navigator.permissions) {
        return await copyTextNew(text);
      } else {
        return await copyTextOld(text);
      }
    }
  } else {
    return await copyTextNew(text);
  }
};

export const snakeToCamel = (str) => {
    return str.replace(/(_\w)/g, function(match) {
        return match[1].toUpperCase();
    });
}

export const camelToSnake = (str) => {
  return str.replace(/[A-Z]/g, function(match) {
      return '_' + match.toLowerCase();
  });
}
