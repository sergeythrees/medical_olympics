import type { CasePublic } from "@/lib/types";

const VITALS: { key: keyof CasePublic["vitals"]; label: string; unit: string }[] = [
  { key: "heart_rate", label: "HR", unit: "/min" },
  { key: "respiratory_rate", label: "RR", unit: "/min" },
  { key: "spo2", label: "SpO₂", unit: "%" },
  { key: "temperature_c", label: "T", unit: "°C" },
];

const FINDING_GROUPS = [
  { kind: "exam", title: "Examination" },
  { kind: "ecg", title: "ECG" },
  { kind: "lab", title: "Laboratory" },
  { kind: "imaging", title: "Imaging" },
  { kind: "other", title: "Other" },
] as const;

export function CaseView({ clinicalCase: c }: { clinicalCase: CasePublic }) {
  const { systolic_bp, diastolic_bp } = c.vitals;
  return (
    <section className="card case-view">
      <h1>{c.title}</h1>
      <p className="muted">
        {c.patient.age}-year-old {c.patient.sex}
      </p>
      <p className="complaint">{c.presenting_complaint}</p>
      <p>{c.history}</p>

      <dl className="vitals">
        {systolic_bp != null && (
          <div>
            <dt>BP</dt>
            <dd>
              {systolic_bp}/{diastolic_bp ?? "?"} mmHg
            </dd>
          </div>
        )}
        {VITALS.map(({ key, label, unit }) =>
          c.vitals[key] == null ? null : (
            <div key={key}>
              <dt>{label}</dt>
              <dd>
                {c.vitals[key]}
                {unit}
              </dd>
            </div>
          ),
        )}
      </dl>

      {FINDING_GROUPS.map(({ kind, title }) => {
        const findings = c.findings.filter((f) => f.kind === kind);
        if (findings.length === 0) return null;
        return (
          <section key={kind}>
            <h2>{title}</h2>
            <table className="findings">
              <tbody>
                {findings.map((f, i) => (
                  <tr key={i}>
                    <th scope="row">{f.name}</th>
                    <td>{f.value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        );
      })}
    </section>
  );
}
