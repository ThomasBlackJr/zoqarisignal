"use client";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Search, ChevronLeft, ChevronRight } from "lucide-react";
import { ManagerPicker } from "@/components/manager-picker";
import { api, Call } from "@/lib/api";
import { CallTable, ErrorBox, Loading, UploadLink } from "@/components/ui";

export default function CallsPage() {
  return (
    <Suspense fallback={<Loading />}>
      <CallsContent />
    </Suspense>
  );
}
function CallsContent() {
  const searchParams = useSearchParams();
  const [error, setError] = useState("");
  const [q, setQ] = useState(searchParams.get("q") ?? "");
  const [flagged, setFlagged] = useState(false);
  const [outdated, setOutdated] = useState(false);
  const [card, setCard] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [cards, setCards] = useState<
    { id: string; name: string; version: string }[]
  >([]);
  useEffect(() => {
    api<typeof cards>("/rubrics")
      .then(setCards)
      .catch((e) => setError(e.message));
  }, []);
  const [filter, setStatus] = useState<string | null>(null);
  const status = filter ?? searchParams.get("status") ?? "";
  const [employee, setEmployee] = useState(
    searchParams.get("employee_id") ?? "",
  );
  const [manager, setManager] = useState(searchParams.get("manager_id") ?? "");
  const [employeeSearch, setEmployeeSearch] = useState("");
  const [employees, setEmployees] = useState<{ id: string; name: string }[]>(
    [],
  );
  useEffect(() => {
    let alive = true;
    const timer = setTimeout(() => {
      api<{ items: { id: string; name: string }[] }>(
        `/employees?q=${encodeURIComponent(employeeSearch)}${manager ? "&manager_id=" + encodeURIComponent(manager) : ""}`,
      )
        .then((v) => {
          if (alive) setEmployees(v.items);
        })
        .catch((e) => {
          if (alive) setError(e.message);
        });
    }, 250);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [employeeSearch, manager]);
  const [sort, setSort] = useState("newest");
  const [review, setReview] = useState(
    searchParams.get("needs_review") === "true",
  );
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<{ items: Call[]; total: number } | null>(
    null,
  );
  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const params = new URLSearchParams({
          q,
          sort,
          needs_review: String(review),
          offset: String(offset),
          limit: "20",
        });
        if (manager) params.set("manager_id", manager);
        if (employee) params.set("employee_id", employee);
        if (status === "processing") params.set("processing", "true");
        else if (status) params.set("status", status);
        if (flagged) params.set("flagged", "true");
        if (outdated) params.set("outdated", "true");
        if (card) params.set("rubric_id", card);
        if (from)
          params.set(
            "date_from",
            String(new Date(from + "T00:00:00").getTime() / 1000),
          );
        if (to)
          params.set(
            "date_to",
            String(new Date(to + "T00:00:00").getTime() / 1000 + 86400),
          );
        const result = await api<{ items: Call[]; total: number }>(
          `/calls?${params}`,
        );
        if (alive) {
          setData(result);
          setError("");
        }
      } catch (e) {
        if (alive) setError((e as Error).message);
      }
    }
    const delay = setTimeout(load, 250);
    const poll = setInterval(load, 5000);
    return () => {
      alive = false;
      clearTimeout(delay);
      clearInterval(poll);
    };
  }, [
    q,
    status,
    offset,
    sort,
    review,
    employee,
    manager,
    flagged,
    outdated,
    card,
    from,
    to,
  ]);
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">CONVERSATION RECORDS</div>
          <h1>Interactions</h1>
          <p>
            Every recording, transcript, and quality review. All in one place.
          </p>
        </div>
        <UploadLink />
      </div>
      <section className="panel">
        <div className="filters">
          <div className="search">
            <Search size={18} />
            <input
              aria-label="Search recordings"
              placeholder="Search audit number, filename or ID…"
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setOffset(0);
              }}
            />
          </div>
          <select
            aria-label="Filter by processing status"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">All statuses</option>
            <option value="processing">Processing (all stages)</option>
            <option value="queued">Awaiting processing</option>
            <option value="transcribing">Transcribing</option>
            <option value="analyzing">Analyzing</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
          </select>
          <select
            aria-label="Sort calls"
            value={sort}
            onChange={(e) => {
              setSort(e.target.value);
              setOffset(0);
            }}
          >
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
            <option value="name">Recording name</option>
          </select>
          <ManagerPicker
            filter
            value={manager}
            onChange={(v) => {
              setManager(v);
              setEmployee("");
              setOffset(0);
            }}
          />
          <input
            aria-label="Find employee filter"
            placeholder="Find employee…"
            value={employeeSearch}
            onChange={(e) => setEmployeeSearch(e.target.value)}
          />
          <select
            aria-label="Filter by employee"
            value={employee}
            onChange={(e) => {
              setEmployee(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">All employees</option>
            {(!manager || manager === "unassigned") && (
              <option value="unassigned">Unassigned</option>
            )}
            {employees.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name}
              </option>
            ))}
          </select>
          <label>
            Scorecard
            <select
              value={card}
              onChange={(e) => {
                setCard(e.target.value);
                setOffset(0);
              }}
            >
              <option value="">All scorecards</option>
              {cards.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} · v{c.version}
                </option>
              ))}
            </select>
          </label>
          <label>
            From
            <input
              type="date"
              value={from}
              onChange={(e) => {
                setFrom(e.target.value);
                setOffset(0);
              }}
            />
          </label>
          <label>
            Through
            <input
              type="date"
              value={to}
              onChange={(e) => {
                setTo(e.target.value);
                setOffset(0);
              }}
            />
          </label>
          <label className="filter-check">
            <input
              type="checkbox"
              checked={flagged}
              onChange={(e) => {
                setFlagged(e.target.checked);
                setOffset(0);
              }}
            />
            Flagged only
          </label>
          <label className="filter-check">
            <input
              type="checkbox"
              checked={outdated}
              onChange={(e) => {
                setOutdated(e.target.checked);
                setOffset(0);
              }}
            />
            Outdated
          </label>
          <label className="filter-check">
            <input
              type="checkbox"
              checked={review}
              onChange={(e) => {
                setReview(e.target.checked);
                setOffset(0);
              }}
            />
            Needs review
          </label>
        </div>
        {error && <ErrorBox message={error} />}
        {searchParams.get("cleanup") === "pending" && (
          <p className="notice">
            Signal data was removed. Recording deletion is pending; the server
            retries cleanup automatically. The recording is no longer accessible
            in Signal.
          </p>
        )}
        {data ? (
          <>
            <CallTable calls={data.items} />
            <div className="pagination">
              <span>
                {data.total
                  ? `${offset + 1}–${Math.min(offset + 20, data.total)} of ${data.total} calls`
                  : "0 calls"}
              </span>
              <div>
                <button
                  className="button secondary"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - 20))}
                >
                  <ChevronLeft size={16} />
                  Previous
                </button>
                <button
                  className="button secondary"
                  disabled={offset + 20 >= data.total}
                  onClick={() => setOffset(offset + 20)}
                >
                  Next
                  <ChevronRight size={16} />
                </button>
              </div>
            </div>
          </>
        ) : (
          <Loading />
        )}
      </section>
    </>
  );
}
