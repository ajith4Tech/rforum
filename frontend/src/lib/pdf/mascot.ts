import { MASCOT_URL } from './constants';

/** Loads the Rforum mascot into a data URI suitable for jsPDF's addImage. Resolves to '' on failure so callers can skip drawing it rather than throw. */
export function loadMascot(): Promise<string> {
  return new Promise<string>((resolve) => {
    const img = new Image();
    img.src = MASCOT_URL;
    img.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = img.width;
      canvas.height = img.height;
      const ctx = canvas.getContext('2d');
      if (ctx) {
        ctx.drawImage(img, 0, 0);
        resolve(canvas.toDataURL('image/png'));
      } else {
        resolve('');
      }
    };
    img.onerror = () => resolve('');
  });
}
