import { notFound } from "next/navigation";

import { AnswerForm } from "@/components/answer-form";
import { CaseView } from "@/components/case-view";
import { api } from "@/lib/api";

export default async function CasePage({ params }: { params: Promise<{ id: string }> }) {
  const caseId = Number((await params).id);
  if (!Number.isInteger(caseId) || caseId <= 0) notFound();

  const { data, response } = await api.GET("/cases/{case_id}", { params: { path: { case_id: caseId } } });
  if (response.status === 404) notFound();
  if (!data) throw new Error(`Failed to load case ${caseId}`);

  return (
    <article className="case-page">
      {/* Server Component: the case text renders on the server and ships no JS. */}
      <CaseView clinicalCase={data} />
      {/* Client island: the only interactive part of the page. */}
      <AnswerForm
        caseId={data.id}
        diagnosisOptions={data.diagnosis_options}
        managementOptions={data.management_options}
      />
    </article>
  );
}
