import { MASCOT_URL } from './constants';

/** Loads a logo image into a data URI suitable for jsPDF's addImage. Defaults
 * to the bundled Rforum mascot; pass the org's branding logo URL to use the
 * configured organization logo instead. Resolves to '' on failure so callers
 * can skip drawing it rather than throw. */
export function loadMascot(url: string = MASCOT_URL): Promise<string> {
  return new Promise<string>((resolve) => {
    const img = new Image();
    img.src = url;
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
