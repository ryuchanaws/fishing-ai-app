import { BrowserRouter, Routes, Route } from "react-router-dom";
import { NavBar } from "./components/NavBar";
import { TopPage } from "./pages/TopPage";
import { MapPage } from "./pages/MapPage";
import { SpotsPage } from "./pages/SpotsPage";
import { FavoritesPage } from "./pages/FavoritesPage";
import "./styles.css";

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-layout">
        <NavBar />
        <main className="main-content">
          <Routes>
            <Route path="/" element={<TopPage />} />
            <Route path="/map" element={<MapPage />} />
            <Route path="/spots" element={<SpotsPage />} />
            <Route path="/favorites" element={<FavoritesPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}