import {
  type ColumnDef,
  type SortingState,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  CheckCircle2,
  CircleAlert,
  Clock3,
  FileSearch,
} from "lucide-react";
import { useMemo, useState } from "react";

import { StatusBadge, type StatusTone } from "../../design-system";
import type { EvidenceFreshness, QueueStatus, ResearchCandidate } from "./model";
import { Sparkline } from "./Sparkline";

const STATUS_LABELS: Record<QueueStatus, string> = {
  new_evidence: "Recent evidence",
  needs_review: "Needs review",
  monitoring: "Monitoring",
};

const STATUS_TONES: Record<QueueStatus, StatusTone> = {
  new_evidence: "info",
  needs_review: "warning",
  monitoring: "neutral",
};

const EVIDENCE_TONES: Record<EvidenceFreshness, StatusTone> = {
  fresh: "positive",
  aging: "warning",
  gap: "negative",
};

function formatPrice(candidate: ResearchCandidate): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: candidate.currency,
    maximumFractionDigits: candidate.currency === "BDT" ? 1 : 2,
  }).format(candidate.price);
}

function SortIndicator({ direction }: { direction: false | "asc" | "desc" }) {
  if (direction === "asc") return <ArrowUp aria-hidden="true" size={12} />;
  if (direction === "desc") return <ArrowDown aria-hidden="true" size={12} />;
  return <ArrowUpDown aria-hidden="true" size={12} />;
}

function EvidenceIcon({ freshness }: { freshness: EvidenceFreshness }) {
  if (freshness === "fresh") return <CheckCircle2 aria-hidden="true" size={13} />;
  if (freshness === "aging") return <Clock3 aria-hidden="true" size={13} />;
  return <CircleAlert aria-hidden="true" size={13} />;
}

export function ResearchQueueTable({
  candidates,
  selectedId,
  onSelect,
}: {
  candidates: readonly ResearchCandidate[];
  selectedId: string | null;
  onSelect: (candidate: ResearchCandidate) => void;
}) {
  const [sorting, setSorting] = useState<SortingState>([{ id: "priority", desc: true }]);
  const columns = useMemo<ColumnDef<ResearchCandidate>[]>(
    () => [
      {
        id: "security",
        header: "Security",
        accessorFn: (candidate) => candidate.ticker,
        cell: ({ row }) => {
          const candidate = row.original;
          return (
            <button className="queue-security" onClick={() => onSelect(candidate)} type="button">
              <span className={`queue-security__market queue-security__market--${candidate.market.toLowerCase()}`}>
                {candidate.market}
              </span>
              <span className="queue-security__identity">
                <strong>{candidate.ticker}</strong>
                <small>{candidate.company}</small>
              </span>
            </button>
          );
        },
      },
      {
        id: "status",
        header: "Workflow",
        accessorKey: "status",
        cell: ({ row }) => (
          <StatusBadge tone={STATUS_TONES[row.original.status]} dot>
            {STATUS_LABELS[row.original.status]}
          </StatusBadge>
        ),
      },
      {
        id: "reason",
        header: "Why it deserves time",
        accessorKey: "queueReason",
        enableSorting: false,
        cell: ({ row }) => <span className="queue-reason">{row.original.queueReason}</span>,
      },
      {
        id: "catalyst",
        header: "Next catalyst",
        accessorFn: (candidate) => candidate.catalyst?.window ?? "",
        enableSorting: false,
        cell: ({ row }) => {
          const catalyst = row.original.catalyst;
          return catalyst ? (
            <span className="queue-catalyst">
              <strong>{catalyst.label}</strong>
              <small>
                {catalyst.window} · {catalyst.confidence}
              </small>
            </span>
          ) : (
            <span className="queue-catalyst">
              <strong>Not confirmed</strong>
              <small>No dated catalyst in the current evidence set</small>
            </span>
          );
        },
      },
      {
        id: "factors",
        header: "Q / V / M / R",
        accessorFn: (candidate) => candidate.factors.quality,
        cell: ({ row }) => (
          <span className="queue-factors" aria-label="Quality, value, momentum, and risk burden">
            <span>{row.original.factors.quality}</span>
            <span>{row.original.factors.value}</span>
            <span>{row.original.factors.momentum}</span>
            <span className="queue-factors__risk">{row.original.factors.risk}</span>
          </span>
        ),
      },
      {
        id: "evidence",
        header: "Evidence",
        accessorFn: (candidate) => candidate.evidence.coveragePct,
        cell: ({ row }) => (
          <span className="queue-evidence">
            <StatusBadge tone={EVIDENCE_TONES[row.original.evidence.freshness]}>
              <EvidenceIcon freshness={row.original.evidence.freshness} />
              {row.original.evidence.coveragePct}%
            </StatusBadge>
            <small>{row.original.evidence.sourceCount} official records</small>
          </span>
        ),
      },
      {
        id: "price",
        header: "Price / trend",
        accessorKey: "price",
        cell: ({ row }) => {
          const candidate = row.original;
          return (
            <span className="queue-price">
              <span>
                <strong className="tnum">{formatPrice(candidate)}</strong>
                  {candidate.dailyChangePct === null ? (
                    <small>change unavailable</small>
                  ) : (
                    <small className={`tnum ${candidate.dailyChangePct >= 0 ? "value-up" : "value-down"}`}>
                      {candidate.dailyChangePct >= 0 ? "+" : ""}
                      {candidate.dailyChangePct.toFixed(1)}%
                    </small>
                  )}
              </span>
              <Sparkline values={candidate.sparkline} positive={(candidate.dailyChangePct ?? 0) >= 0} />
            </span>
          );
        },
      },
      {
        id: "priority",
        header: "Priority",
        accessorKey: "priority",
        cell: ({ row }) => (
          <span className="queue-priority">
            <strong className="tnum">{row.original.priority}</strong>
            <span aria-hidden="true" className="queue-priority__track">
              <span style={{ width: `${row.original.priority}%` }} />
            </span>
          </span>
        ),
      },
    ],
    [onSelect],
  );
  const data = useMemo(() => [...candidates], [candidates]);

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  return (
    <div className="queue-table-wrap">
      <table className="queue-table">
        <thead>
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <th key={header.id} scope="col">
                  {header.isPlaceholder ? null : header.column.getCanSort() ? (
                    <button
                      className="queue-table__sort"
                      onClick={header.column.getToggleSortingHandler()}
                      type="button"
                    >
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      <SortIndicator direction={header.column.getIsSorted()} />
                    </button>
                  ) : (
                    flexRender(header.column.columnDef.header, header.getContext())
                  )}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr
              aria-selected={selectedId === row.original.id}
              className={selectedId === row.original.id ? "queue-table__row--selected" : ""}
              key={row.id}
              onClick={() => onSelect(row.original)}
            >
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {candidates.length === 0 && (
        <div className="queue-empty">
          <FileSearch aria-hidden="true" size={22} />
          <strong>No securities match this view</strong>
          <span>Adjust the mandate, workflow state, or search.</span>
        </div>
      )}
    </div>
  );
}
