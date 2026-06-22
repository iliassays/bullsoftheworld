import { Route, Routes } from "react-router-dom";
import { Shell } from "./components/Shell";
import { Feed } from "./pages/Feed";
import { Markets } from "./pages/Markets";
import { Profile } from "./pages/Profile";
import { SymbolPage } from "./pages/Symbol";
import { Watchlist } from "./pages/Watchlist";

export function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Feed />} />
        <Route path="markets" element={<Markets />} />
        <Route path="watchlist" element={<Watchlist />} />
        <Route path="s/:code" element={<SymbolPage />} />
        <Route path="me" element={<Profile />} />
      </Route>
    </Routes>
  );
}
