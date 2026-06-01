export default function LivePreview({ code }) {
  // We wrap the raw code from the editor in a full HTML document.
  // We also inject the Tailwind CSS CDN so any styling the AI writes automatically works!
  const srcDoc = `
    <!DOCTYPE html>
    <html lang="en">
      <head>
        <meta charset="UTF-8">
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
          /* Hide scrollbars for a cleaner look but allow scrolling */
          body { margin: 0; display: flex; justify-content: center; align-items: center; min-height: 100vh; background-color: #f9fafb; font-family: sans-serif; }
          ::-webkit-scrollbar { width: 8px; height: 8px; }
          ::-webkit-scrollbar-thumb { background: #ccc; border-radius: 4px; }
        </style>
      </head>
      <body>
        ${code}
      </body>
    </html>
  `;

  return (
    <div className="w-full h-full bg-white">
      <iframe
        srcDoc={srcDoc}
        title="Live Preview"
        sandbox="allow-scripts" // This allows JavaScript to run safely inside the preview
        className="w-full h-full border-none"
      />
    </div>
  );
}