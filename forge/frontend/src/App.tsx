import { Routes, Route, Navigate } from "react-router-dom";
import { AnimatePresence } from "framer-motion";
import Dashboard from "./pages/Dashboard";
import Chat from "./pages/Chat";
import Approval from "./pages/Approval";
import Pipeline from "./pages/Pipeline";
import Results from "./pages/Results";
import Graph from "./pages/Graph";
import CodeGen from "./pages/CodeGen";
import DiffApproval from "./pages/DiffApproval";

export default function App() {
  return (
    <AnimatePresence mode="wait">
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/chat/:pipelineId?" element={<Chat />} />
        <Route path="/approval/:pipelineId" element={<Approval />} />
        <Route path="/pipeline/:pipelineId" element={<Pipeline />} />
        <Route path="/results/:pipelineId" element={<Results />} />
        <Route path="/gen/:pipelineId" element={<CodeGen />} />
        <Route path="/gen/:codegenId/approve" element={<DiffApproval />} />
        <Route path="/explore" element={<Graph />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AnimatePresence>
  );
}
