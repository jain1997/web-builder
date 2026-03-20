import JSZip from "jszip";

export async function downloadAsZip(
  files: Record<string, string>,
  filename = "project.zip"
): Promise<void> {
  const zip = new JSZip();

  for (const [path, content] of Object.entries(files)) {
    if (content.startsWith("data:image/")) {
      // Image data URI — decode to binary PNG in the ZIP
      const base64 = content.split(",")[1];
      if (base64) {
        zip.file(path, base64, { base64: true });
      }
    } else {
      zip.file(path, content);
    }
  }

  const blob = await zip.generateAsync({ type: "blob" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
