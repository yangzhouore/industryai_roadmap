'use client';
export default function ErrorPage({reset}:{reset:()=>void}){return <main id="main" className="page prose"><h1>Unable to load this edition / 暂时无法加载</h1><p>Please try again. / 请稍后重试。</p><button onClick={reset}>Try again / 重试</button></main>;}
