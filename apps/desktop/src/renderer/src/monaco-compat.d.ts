// @monaco-editor/react 4.7 的声明仍引用旧 Monaco 子路径和 React 全局 JSX。
// Adapt its legacy declarations to Monaco's exported types and React 19's scoped JSX.
declare module 'monaco-editor/esm/vs/editor/editor.api' {
  export * from 'monaco-editor'
}

declare namespace JSX {
  type Element = import('react').JSX.Element
}
