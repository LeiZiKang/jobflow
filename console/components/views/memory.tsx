"use client";

import { useMemo, useState } from "react";
import { fullDate } from "@/lib/format";
import type { MemoryDocument, MemoryItem } from "@/lib/types";
import { Count, Empty, Panel, Pill, Refs } from "../primitives";

type Filter = "全部" | "accepted" | "proposed";

export function MemoryView({ memory }: { memory: MemoryDocument }) {
  const [filter, setFilter] = useState<Filter>("全部");
  const items = useMemo(() => memory.items ?? [], [memory.items]);
  const counts = memory.counts ?? {};

  const visible = useMemo(
    () => (filter === "全部" ? items : items.filter((item) => item.status === filter)),
    [items, filter]
  );

  return (
    <>
      <div className="toolbar">
        {(["全部", "accepted", "proposed"] as Filter[]).map((value) => (
          <button
            key={value}
            type="button"
            className="toggle"
            aria-pressed={filter === value}
            onClick={() => setFilter(value)}
          >
            {value === "全部" ? "全部" : value === "accepted" ? `已接受 ${counts.accepted ?? 0}` : `待评审 ${counts.proposed ?? 0}`}
          </button>
        ))}
        <span className="faint mono" style={{ fontSize: "var(--fs1)", marginLeft: "auto" }}>
          revision {memory.revision ?? "—"} · {fullDate(memory.updated_at)}
        </span>
      </div>

      {counts.proposed ? (
        <p className="banner banner--warn">
          <b>{counts.proposed} 条待评审</b>
          <span>Agent 只能提出 proposed；没评审过的不会进新 Agent 的 context。</span>
        </p>
      ) : null}

      <Panel title="长期记忆" meta={<Count value={visible.length} />} flush>
        {visible.length ? (
          <div>
            {visible.map((item) => (
              <MemoryRow key={item.memory_id} item={item} />
            ))}
          </div>
        ) : (
          <Empty>这个筛选下没有记忆。</Empty>
        )}
      </Panel>
    </>
  );
}

function MemoryRow({ item }: { item: MemoryItem }) {
  return (
    <article className="mem">
      <div className="mem__head">
        <h3 className="mem__subject">{item.subject}</h3>
        <Pill status={item.status} />
      </div>
      <p className="mem__statement">{item.statement}</p>
      {item.source_refs?.length ? (
        <div style={{ marginTop: "var(--s3)" }}>
          <Refs items={item.source_refs} />
        </div>
      ) : null}
      <p className="mem__foot">
        <span>{item.memory_id}</span>
        <span>{item.type}</span>
        <span>{item.scope}</span>
        {item.evidence_strength ? <span>{item.evidence_strength}</span> : null}
        {item.author?.id ? <span>by {item.author.id}</span> : null}
        {item.tags?.length ? <span>#{item.tags.join(" #")}</span> : null}
        {item.valid_until ? <span>有效期至 {fullDate(item.valid_until)}</span> : null}
      </p>
    </article>
  );
}
