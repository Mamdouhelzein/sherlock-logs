import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowUpRight, Search, X, type LucideIcon } from "lucide-react";

type Destination = { to: string; label: string; icon: LucideIcon };

export function CommandMenu({ items }: { items: Destination[] }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [search, setSearch] = useState("");
  const navigate = useNavigate();
  const matches = items.filter((item) =>
    item.label.toLowerCase().includes(search.toLowerCase().trim()),
  );

  useEffect(() => {
    function shortcut(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        if (dialog.current?.open) dialog.current.close();
        else dialog.current?.showModal();
      }
    }
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, []);

  return (
    <>
      <button
        className="command-trigger"
        onClick={() => dialog.current?.showModal()}
        aria-label="Open navigation search"
      >
        <Search size={15} aria-hidden="true" />
        <span>Jump to a page</span>
        <kbd>⌘ / Ctrl K</kbd>
      </button>
      <dialog
        ref={dialog}
        className="command-dialog"
        aria-labelledby="command-title"
        onClose={() => setSearch("")}
      >
        <h2 id="command-title" className="sr-only">
          Jump to a page
        </h2>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (matches[0]) {
              navigate(matches[0].to);
              dialog.current?.close();
            }
          }}
        >
          <div className="command-input-row">
            <Search size={20} aria-hidden="true" />
            <input
              autoFocus
              aria-label="Search pages"
              placeholder="Where would you like to go?"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <button
              type="button"
              aria-label="Close navigation search"
              onClick={() => dialog.current?.close()}
            >
              <X size={18} aria-hidden="true" />
            </button>
          </div>
        </form>
        <div className="command-results">
          <span className="command-caption mono">WORKSPACE PAGES</span>
          <ul>
            {matches.map(({ to, label, icon: Icon }) => (
              <li key={to}>
                <Link to={to} onClick={() => dialog.current?.close()}>
                  <Icon size={19} aria-hidden="true" />
                  <span>{label}</span>
                  <ArrowUpRight size={15} aria-hidden="true" />
                </Link>
              </li>
            ))}
          </ul>
          {matches.length === 0 && (
            <p className="command-empty" role="status">
              No matching pages. Try “setup” or “overview”.
            </p>
          )}
        </div>
        <div className="command-footer">
          <span>
            <kbd>Tab</kbd> to select <kbd>Enter</kbd> to open
          </span>
          <span>
            <kbd>Esc</kbd> to close
          </span>
        </div>
      </dialog>
    </>
  );
}
