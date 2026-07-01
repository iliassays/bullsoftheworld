import { Route, Routes } from "react-router-dom";
import { About } from "./pages/About";
import { Shell } from "./components/Shell";
import { ForgotPassword, ResetPassword, VerifyEmail } from "./pages/AuthFlows";
import { BullsFeed } from "./pages/BullsFeed";
import { DeskProfile } from "./pages/DeskProfile";
import { Feed } from "./pages/Feed";
import { Markets } from "./pages/Markets";
import { Profile } from "./pages/Profile";
import { ScreenExplore } from "./pages/ScreenExplore";
import { SymbolPage } from "./pages/Symbol";
import { Watchlist } from "./pages/Watchlist";

export function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Feed />} />
        <Route path="markets" element={<Markets />} />
        <Route path="markets/:key" element={<ScreenExplore />} />
        <Route path="bulls" element={<BullsFeed />} />
        <Route path="desk/:handle" element={<DeskProfile />} />
        <Route path="watchlist" element={<Watchlist />} />
        <Route path="s/:code" element={<SymbolPage />} />
        <Route path="me" element={<Profile />} />
        <Route path="about" element={<About />} />
        <Route path="forgot" element={<ForgotPassword />} />
        <Route path="reset" element={<ResetPassword />} />
        <Route path="verify" element={<VerifyEmail />} />
      </Route>
    </Routes>
  );
}
