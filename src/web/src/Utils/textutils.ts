import { isMobile } from "react-device-detect";
import { inWechat } from 'constants/uiConstants';

const isSafari = navigator.userAgent.match(/iPad|iPhone|iPod|Macintosh/i);

const copyViaExecCommand = async (text: string): Promise<void> => {
  return new Promise<void>((resolve) => {
    const textArea = document.createElement("textarea") as HTMLTextAreaElement;
    textArea.value = text;
    textArea.style.width = '0';
    textArea.style.position = "fixed";
    textArea.style.left = "-999px";
    textArea.style.top = "10px";
    textArea.setAttribute("readonly", "readonly");
    document.body.appendChild(textArea);

    textArea.select();
    document.execCommand("copy");
    document.body.removeChild(textArea);
    resolve();
  });
};

const copyViaClipboardAPI = async (text: string): Promise<void> => {
  return navigator.clipboard.writeText(text);
};

export const copyText = async (text: string): Promise<void> => {
  if (isMobile) {
    if (inWechat()) {
      if (navigator.clipboard && isSafari) {
        return copyViaClipboardAPI(text);
      } else {
        return copyViaExecCommand(text);
      }
    } else {
      if (navigator.clipboard && navigator.permissions) {
        return await copyViaClipboardAPI(text);
      } else {
        return await copyViaExecCommand(text);
      }
    }
  } else {
    return await copyViaClipboardAPI(text);
  }
};

export const snakeToCamel = (str: string): string => {
    return str.replace(/(_\w)/g, function(match: string): string {
        return match[1].toUpperCase();
    });
};

export const camelToSnake = (str: string): string => {
  return str.replace(/[A-Z]/g, function(match: string): string {
      return '_' + match.toLowerCase();
  });
};
