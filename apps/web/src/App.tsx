import { Navigate, Route, Routes } from "react-router-dom";
import { About } from "./pages/About";
import { Shell } from "./components/Shell";
import { Alerts } from "./pages/Alerts";
import { ForgotPassword, ResetPassword, VerifyEmail } from "./pages/AuthFlows";
import { DeskProfile } from "./pages/DeskProfile";
import { Feed } from "./pages/Feed";
import { Markets } from "./pages/Markets";
import { PatternDetail } from "./pages/PatternDetail";
import { PatternLibrary } from "./pages/PatternLibrary";
import { Portfolio } from "./pages/Portfolio";
import { Scanner } from "./pages/Scanner";
import { Profile } from "./pages/Profile";
import { ScreenExplore } from "./pages/ScreenExplore";
import { SymbolPage } from "./pages/Symbol";
import { UserProfile } from "./pages/UserProfile";
import { Watchlist } from "./pages/Watchlist";
import { Welcome } from "./pages/Welcome";

export function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Feed />} />
        <Route path="markets" element={<Markets />} />
        <Route path="markets/:key" element={<ScreenExplore />} />
        <Route path="learn/patterns" element={<PatternLibrary />} />
        <Route path="learn/patterns/:type" element={<PatternDetail />} />
        <Route path="ideas" element={<Scanner />} />
        <Route path="portfolio" element={<Portfolio />} />
        <Route path="alerts" element={<Alerts />} />
        {/* Redesign 2026-07: Bulls tab merged into Home (desks filter chip); Scanner renamed Ideas. */}
        <Route path="bulls" element={<Navigate to="/?feed=desks" replace />} />
        <Route path="scanner" element={<Navigate to="/ideas" replace />} />
        <Route path="desk/:handle" element={<DeskProfile />} />
        <Route path="u/:handle" element={<UserProfile />} />
        <Route path="watchlist" element={<Watchlist />} />
        <Route path="s/:code" element={<SymbolPage />} />
        <Route path="me" element={<Profile />} />
        <Route path="welcome" element={<Welcome />} />
        <Route path="about" element={<About />} />
        <Route path="forgot" element={<ForgotPassword />} />
        <Route path="reset" element={<ResetPassword />} />
        <Route path="verify" element={<VerifyEmail />} />
      </Route>
    </Routes>
  );
}
