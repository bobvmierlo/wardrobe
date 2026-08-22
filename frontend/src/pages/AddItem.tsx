import { useNavigate } from "react-router-dom";
import { api } from "../api";
import ItemForm from "../components/ItemForm";
import AppFooter from "../components/AppFooter";
import { useWardrobe } from "../wardrobe";

export default function AddItem() {
  const navigate = useNavigate();
  const { current, canEdit, isShared } = useWardrobe();

  return (
    <div className="app">
      <div className="topbar">
        <button className="btn-ghost" onClick={() => navigate(-1)}>
          ← Terug
        </button>
        <h1>Nieuw stuk</h1>
        <span style={{ width: 64 }} />
      </div>
      <div className="content">
        {!canEdit ? (
          <div className="empty">
            <div className="big">🔒</div>
            <p>Je hebt alleen-lezen toegang tot deze kast.</p>
            <p className="muted">Je kunt combinaties beoordelen, maar geen kledingstukken toevoegen.</p>
          </div>
        ) : (
          <ItemForm
            submitLabel={isShared && current ? `Toevoegen aan ${current.name}` : "Toevoegen aan kast"}
            onSubmit={async (form) => {
              const item = await api.createItem(current!.id, form);
              navigate(`/item/${item.id}`, { replace: true });
            }}
          />
        )}
        <AppFooter />
      </div>
    </div>
  );
}
