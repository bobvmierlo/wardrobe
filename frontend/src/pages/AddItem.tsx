import { useNavigate } from "react-router-dom";
import { api } from "../api";
import ItemForm from "../components/ItemForm";

export default function AddItem() {
  const navigate = useNavigate();

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
        <ItemForm
          submitLabel="Toevoegen aan kast"
          onSubmit={async (form) => {
            const item = await api.createItem(form);
            navigate(`/item/${item.id}`, { replace: true });
          }}
        />
      </div>
    </div>
  );
}
