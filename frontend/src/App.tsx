import { Routes, Route } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";
import { LiveFeed } from "./pages/LiveFeed";
import { ReviewInspector } from "./pages/ReviewInspector";
import { CostAnalytics } from "./pages/CostAnalytics";
import { QualityMetrics } from "./pages/QualityMetrics";

export default function App() {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <Routes>
          <Route path="/" element={<LiveFeed />} />
          <Route path="/inspect" element={<ReviewInspector />} />
          <Route path="/inspect/:jobId" element={<ReviewInspector />} />
          <Route path="/cost" element={<CostAnalytics />} />
          <Route path="/quality" element={<QualityMetrics />} />
        </Routes>
      </main>
    </div>
  );
}
