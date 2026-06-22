import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Route, Routes } from "react-router-dom";
import { Shell } from "./components/Shell";
import { Feed } from "./pages/Feed";
import { Markets } from "./pages/Markets";
import { Profile } from "./pages/Profile";
import { SymbolPage } from "./pages/Symbol";
import { Watchlist } from "./pages/Watchlist";
export function App() {
    return (_jsx(Routes, { children: _jsxs(Route, { element: _jsx(Shell, {}), children: [_jsx(Route, { index: true, element: _jsx(Feed, {}) }), _jsx(Route, { path: "markets", element: _jsx(Markets, {}) }), _jsx(Route, { path: "watchlist", element: _jsx(Watchlist, {}) }), _jsx(Route, { path: "s/:code", element: _jsx(SymbolPage, {}) }), _jsx(Route, { path: "me", element: _jsx(Profile, {}) })] }) }));
}
