"use client";
import { useEffect, useState } from "react";
import { api, Rubric, RubricCategory } from "@/lib/api";
import { useDrive } from "@/components/shell";
import { Dialog } from "@/components/dialog";
import { ErrorBox, Loading } from "@/components/ui";
import { Plus, ArrowUp, ArrowDown, Copy, BookOpen } from "lucide-react";

export default function RubricsPage() {
  const { user } = useDrive();
  const admin = ["ADMIN", "OWNER"].includes(user.role);
  const [rubrics, setRubrics] = useState<Rubric[] | null>(null);
  const [selected, setSelected] = useState<Rubric | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    api<Rubric[]>("/rubrics")
      .then(setRubrics)
      .catch((e) => setError(e.message));
  }, []);
  const total = selected?.categories.reduce((n, c) => n + c.weight, 0) ?? 0;
  const editable = admin && selected?.status === "DRAFT";
  async function action(path: string, body?: unknown, method = "POST") {
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const result = await api<Rubric>(path, {
        method,
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      setSelected(result);
      setDirty(false);
      setConfirm(false);
      setRubrics(await api<Rubric[]>("/rubrics"));
      setMessage(
        method === "PUT"
          ? "Draft saved."
          : path.endsWith("activate")
            ? "Scorecard published. Historical evaluations are unchanged."
            : "Scorecard updated.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  function category(i: number, patch: Partial<RubricCategory>) {
    if (!selected) return;
    setSelected({
      ...selected,
      categories: selected.categories.map((c, j) =>
        i === j ? { ...c, ...patch } : c,
      ),
    });
    setDirty(true);
  }
  function move(i: number, delta: number) {
    if (!selected) return;
    const cs = [...selected.categories];
    [cs[i], cs[i + delta]] = [cs[i + delta], cs[i]];
    setSelected({ ...selected, categories: cs });
    setDirty(true);
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">
            {admin ? "ADMINISTRATION" : "QUALITY STANDARDS"}
          </div>
          <h1>Scorecards</h1>
          <p>
            Define service quality. Keep every evaluation tied to its original
            standard.
          </p>
        </div>
        {admin && (
          <button
            className="button primary"
            disabled={saving || dirty}
            onClick={() =>
              action("/rubrics", { name: "Dispatch QA", categories: [] })
            }
          >
            <Plus size={17} />
            New scorecard
          </button>
        )}
      </div>
      {error && <ErrorBox message={error} />}{" "}
      {message && (
        <p className="success-message" role="status">
          {message}
        </p>
      )}
      {!rubrics ? (
        <Loading />
      ) : (
        <div className="rubric-layout">
          <aside className="panel rubric-list">
            <div className="panel-heading">
              <h2>Versions</h2>
              <BookOpen size={18} />
            </div>
            {rubrics.map((r) => (
              <button
                key={r.id}
                className={`rubric-version ${selected?.id === r.id ? "selected" : ""}`}
                disabled={dirty || saving}
                onClick={() => {
                  setSelected(r);
                  setMessage("");
                }}
              >
                <span>
                  <strong>{r.name}</strong>
                  <small>
                    Version {r.version} · {r.categories.length} categories
                  </small>
                </span>
                <span className={`rubric-status ${r.status.toLowerCase()}`}>
                  {r.status === "ACTIVE" ? "PUBLISHED" : r.status}
                </span>
              </button>
            ))}
          </aside>
          <section className="panel rubric-editor">
            {selected ? (
              <>
                <div className="panel-heading">
                  <div>
                    <h2>{selected.name}</h2>
                    <p>
                      Version {selected.version} ·{" "}
                      {editable
                        ? "Editable draft"
                        : "Published content is immutable"}
                    </p>
                  </div>
                  <span
                    className={`rubric-status ${selected.status.toLowerCase()}`}
                  >
                    {selected.status === "ACTIVE"
                      ? "PUBLISHED"
                      : selected.status}
                  </span>
                </div>
                <div
                  className={`weight-total ${total === 100 ? "valid" : "invalid"}`}
                  role="status"
                >
                  <span>TOTAL WEIGHT</span>
                  <strong>{total} / 100</strong>
                  <small>
                    {total === 100
                      ? "Ready for publication"
                      : "Must equal 100 to publish"}
                  </small>
                </div>
                <form
                  className="rubric-form"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void action(
                      `/rubrics/${selected.id}`,
                      {
                        name: selected.name,
                        revision: selected.revision,
                        categories: selected.categories.map((c) => ({
                          key: c.key,
                          name: c.name,
                          description: c.description,
                          weight: c.weight,
                          criteria: c.criteria,
                        })),
                      },
                      "PUT",
                    );
                  }}
                >
                  <label>
                    Scorecard name
                    <input
                      required
                      maxLength={120}
                      value={selected.name}
                      disabled={!editable || saving}
                      onChange={(e) => {
                        setSelected({ ...selected, name: e.target.value });
                        setDirty(true);
                      }}
                    />
                  </label>
                  {selected.categories.map((c, i) => (
                    <fieldset
                      className="rubric-category"
                      key={c.key ?? `new-${i}`}
                      disabled={!editable || saving}
                    >
                      <legend>Category {i + 1}</legend>
                      <div className="category-fields">
                        <label>
                          Category name
                          <input
                            required
                            maxLength={120}
                            value={c.name}
                            onChange={(e) =>
                              category(i, { name: e.target.value })
                            }
                          />
                        </label>
                        <label>
                          Weight / points
                          <input
                            required
                            type="number"
                            min={1}
                            max={100}
                            step={1}
                            value={c.weight}
                            onChange={(e) =>
                              category(i, { weight: Number(e.target.value) })
                            }
                          />
                        </label>
                      </div>
                      <label>
                        Description
                        <textarea
                          rows={2}
                          maxLength={2000}
                          value={c.description}
                          onChange={(e) =>
                            category(i, { description: e.target.value })
                          }
                        />
                      </label>
                      <label>
                        Evaluation criteria
                        <textarea
                          rows={3}
                          required
                          maxLength={5000}
                          value={c.criteria}
                          onChange={(e) =>
                            category(i, { criteria: e.target.value })
                          }
                        />
                      </label>
                      {editable && (
                        <div className="form-actions">
                          <button
                            type="button"
                            className="button secondary"
                            aria-label={`Move category ${i + 1} up`}
                            disabled={i === 0}
                            onClick={() => move(i, -1)}
                          >
                            <ArrowUp size={16} />
                            Up
                          </button>
                          <button
                            type="button"
                            className="button secondary"
                            aria-label={`Move category ${i + 1} down`}
                            disabled={i === selected.categories.length - 1}
                            onClick={() => move(i, 1)}
                          >
                            <ArrowDown size={16} />
                            Down
                          </button>
                          <button
                            type="button"
                            className="text-link danger-text"
                            onClick={() => {
                              setSelected({
                                ...selected,
                                categories: selected.categories.filter(
                                  (_, j) => i !== j,
                                ),
                              });
                              setDirty(true);
                            }}
                          >
                            Remove category
                          </button>
                        </div>
                      )}
                    </fieldset>
                  ))}
                  {editable && (
                    <>
                      <button
                        type="button"
                        className="button secondary"
                        disabled={saving || selected.categories.length >= 30}
                        onClick={() => {
                          setSelected({
                            ...selected,
                            categories: [
                              ...selected.categories,
                              {
                                name: "New category",
                                description: "",
                                criteria:
                                  "Evaluate this category using transcript evidence.",
                                weight: 10,
                              },
                            ],
                          });
                          setDirty(true);
                        }}
                      >
                        <Plus size={16} />
                        Add category
                      </button>
                      <div className="editor-actions">
                        <span>{dirty ? "Unsaved changes" : "Draft saved"}</span>
                        <div className="form-actions">
                          <button
                            type="button"
                            className="button secondary"
                            disabled={saving || !dirty}
                            onClick={() => {
                              setSelected(
                                rubrics.find((r) => r.id === selected.id) ??
                                  null,
                              );
                              setDirty(false);
                            }}
                          >
                            Discard edits
                          </button>
                          <button
                            className="button primary"
                            disabled={saving || !dirty}
                          >
                            Save draft
                          </button>
                          <button
                            type="button"
                            className="button secondary"
                            disabled={saving || dirty || total !== 100}
                            onClick={() => setConfirm(true)}
                          >
                            Publish scorecard
                          </button>
                        </div>
                      </div>
                    </>
                  )}
                </form>
                {admin && (
                  <div className="panel-foot">
                    <button
                      className="text-link"
                      disabled={saving || dirty}
                      onClick={() =>
                        action(`/rubrics/${selected.id}/duplicate`)
                      }
                    >
                      <Copy size={15} />
                      Duplicate as draft
                    </button>
                    {selected.status !== "ARCHIVED" && (
                      <button
                        className="text-link"
                        disabled={saving || dirty}
                        onClick={() =>
                          action(`/rubrics/${selected.id}/archive`, {
                            revision: selected.revision,
                          })
                        }
                      >
                        Archive scorecard
                      </button>
                    )}
                  </div>
                )}
              </>
            ) : (
              <div className="empty">
                <BookOpen size={30} />
                <h3>Select a scorecard version</h3>
                <p>
                  Review a published standard or open a draft to make changes.
                </p>
              </div>
            )}
          </section>
        </div>
      )}
      {confirm && selected && (
        <Dialog
          title="Publish this scorecard?"
          onClose={() => !saving && setConfirm(false)}
        >
          <p>
            <strong>
              {selected.name} · Version {selected.version}
            </strong>{" "}
            will be available for selection as a published 100-point scorecard.
            Other published versions remain available until explicitly archived.
          </p>
          <p>
            Evaluations selecting this scorecard will use this exact version.
            Existing evaluations and scores remain unchanged. Published
            categories cannot be edited.
          </p>
          {error && <ErrorBox message={error} />}
          <div className="form-actions">
            <button
              className="button secondary"
              disabled={saving}
              onClick={() => setConfirm(false)}
            >
              Cancel
            </button>
            <button
              className="button primary"
              disabled={saving}
              onClick={() =>
                action(`/rubrics/${selected.id}/activate`, {
                  revision: selected.revision,
                })
              }
            >
              Confirm publication
            </button>
          </div>
        </Dialog>
      )}
    </>
  );
}
