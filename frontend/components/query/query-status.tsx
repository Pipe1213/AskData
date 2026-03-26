type QueryStatusProps = {
  title: string;
  description: string;
  tone?: "info" | "success";
};

export function QueryStatus({
  title,
  description,
  tone = "info",
}: QueryStatusProps) {
  const toneClass =
    tone === "success"
      ? "border-success/20 bg-success/10 text-success"
      : "border-info/20 bg-info/10 text-info";

  return (
    <section className={`panel flex items-start gap-4 p-5 ${toneClass}`}>
      <div className="rounded-full border border-current/20 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em]">
        {tone}
      </div>
      <div>
        <h2 className="text-lg font-semibold leading-tight">{title}</h2>
        <p className="mt-2 text-sm leading-6 text-ink/80">{description}</p>
      </div>
    </section>
  );
}
