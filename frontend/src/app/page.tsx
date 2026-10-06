import Link from "next/link";

import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const { data: cases, error } = await api.GET("/cases");
  if (error || !cases) throw new Error("Failed to load cases");

  return (
    <>
      <h1>Clinical cases</h1>
      {cases.length === 0 && <p className="muted">No cases yet.</p>}
      <ul className="case-list">
        {cases.map((c) => (
          <li key={c.id}>
            <Link href={`/cases/${c.id}`} className="card case-link">
              <strong>{c.title}</strong>
              <span className="muted">
                {c.patient.age} y/o {c.patient.sex} · {c.presenting_complaint}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}
