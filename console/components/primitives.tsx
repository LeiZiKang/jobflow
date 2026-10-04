import type { ReactNode } from "react";
import { statusLabel, statusTone } from "@/lib/format";

export function Pill({ status, label }: { status?: string; label?: string }) {
  return <span className={`pill pill--${statusTone(status)}`}>{label ?? statusLabel(status)}</span>;
}

export function Panel({
  title,
  meta,
  action,
  flush,
  children,
}: {
  title: string;
  meta?: ReactNode;
  action?: ReactNode;
  flush?: boolean;
  children: ReactNode;
}) {
  return (
    <section className="panel">
      <div className="panel__head">
        <h2>{title}</h2>
        <div className="row__right">
          {meta}
          {action}
        </div>
      </div>
      <div className={flush ? "panel__body panel__body--flush" : "panel__body"}>{children}</div>
    </section>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>;
}

export function Count({ value }: { value: number }) {
  return <span className="count num">{value}</span>;
}

export function Chips({ label, items, tone }: { label: string; items?: string[]; tone?: "allow" | "deny" }) {
  if (!items?.length) return null;
  const className = tone ? `chip chip--${tone}` : "chip";
  return (
    <div className="chips">
      <span className="chips__label">{label}</span>
      {items.map((item) => (
        <span className={className} key={item}>
          {item}
        </span>
      ))}
    </div>
  );
}

export function Subhead({ title, meta }: { title: string; meta?: ReactNode }) {
  return (
    <div className="subhead">
      <h4>{title}</h4>
      {meta}
    </div>
  );
}

export function Refs({ items }: { items?: string[] }) {
  if (!items?.length) return null;
  return (
    <div className="refs">
      {items.map((item) => (
        <code key={item}>{item}</code>
      ))}
    </div>
  );
}

export function Bullets({ items }: { items?: string[] }) {
  if (!items?.length) return null;
  return (
    <ul className="bullets">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}
