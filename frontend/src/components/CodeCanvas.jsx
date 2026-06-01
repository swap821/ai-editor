import Editor from '@monaco-editor/react';

export default function CodeCanvas({ code, onChange, language }) {
  return (
    <div className="w-full h-full">
      <Editor
        height="100%"
        width="100%"
        theme="vs-dark"
        language={language} // NEW: The editor now listens for language changes
        value={code}
        onChange={onChange}
        options={{
          minimap: { enabled: false },
          fontSize: 14,
          wordWrap: 'on',
          padding: { top: 16 },
          smoothScrolling: true,
          cursorBlinking: "smooth",
        }}
      />
    </div>
  );
}