"use client";

export default function Error({ reset }: { error: Error; reset: () => void }) {
  return (
    <div role="alert">
      <h1>Something went wrong</h1>
      <p className="muted">The cases service did not respond.</p>
      <button onClick={reset}>Try again</button>
    </div>
  );
}
