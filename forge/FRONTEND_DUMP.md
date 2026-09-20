# Forge Frontend - Complete Dump for Redesign

This document contains the complete current frontend code for reference during redesign.

## Current Structure

```
forge/frontend/src/
├── main.tsx              # React entry point
├── App.tsx               # Main app with Graph/Analyst tabs
├── types.ts              # TypeScript types
├── api.ts                # API client
├── index.css             # All styles (54KB, ~2300 lines)
├── components/
│   ├── TopBar.tsx        # Header with page tabs
│   ├── IconRail.tsx      # Left sidebar icons
│   ├── CommandBar.tsx    # Floating query input
│   ├── ImpactAnalyst.tsx # Main pipeline UI (largest)
│   ├── IngestPanel.tsx   # Repo ingestion form
│   ├── ResultsDrawer.tsx # Bottom sheet for results
│   ├── DetailsPanel.tsx  # Node details sidebar
│   ├── LegendBar.tsx     # Graph legend
│   ├── HealthIndicator.tsx # Backend status
│   └── primitives.tsx    # Drawer, Chip, Banner
└── graph/
    ├── GraphCanvas.tsx   # Cytoscape canvas
    ├── cytoConfig.ts     # Node/edge styling
    ├── useBlastRadius.ts # Query hook
    └── animateTraversal.ts
```

## Pages

### 1. Graph Explorer (`page === "graph"`)
- Interactive Cytoscape graph of services/functions
- Command bar for "what breaks if" queries
- Left drawers: Ingest, Legend
- Right drawer: Node details
- Bottom sheet: Query results

### 2. Impact Analyst (`page === "analyst"`)
- 3-column layout: Requirements | Conversation/Loading/Report | Summary
- Pipeline stages: gathering → requirements_ready → analyzing → verifying → awaiting_approval
- Chat interface for context gathering
- Loading screen with funny messages
- Report approval view

---

## API Endpoints Used

```typescript
// Graph
GET  /health
GET  /graph/overview
GET  /graph/service/{id}
GET  /graph/symbol/{id}
GET  /graph/stats

// Chat (Q&A mode)
POST /impact/chat
DELETE /impact/chat/{session_id}

// Pipeline (multi-agent)
POST /pipeline/start
POST /pipeline/{id}/respond
POST /pipeline/{id}/confirm
GET  /pipeline/{id}
POST /pipeline/{id}/approve
DELETE /pipeline/{id}
```

---

## Known Issues / Pain Points

1. **54KB CSS file** - monolithic, hard to maintain
2. **ImpactAnalyst.tsx is 700+ lines** - doing too much
3. **Graph and Analyst are separate pages** - could be unified
4. **Loading messages are cheesy** - "🤔 Pondering your requirements..."
5. **Report display is just `<pre>`** - no formatting
6. **Hallucinated services** - LLM invents services like "verification-agent"
7. **No graph visualization in Analyst** - missed opportunity
8. **Mobile responsiveness is basic** - needs work

---

## Design Tokens (from CSS)

```css
:root {
  /* Dark chrome */
  --chrome-bg: #0b0f17;
  --chrome-bg-raised: #131a26;
  --chrome-border: #232b3a;
  --text-primary: #f1f4f9;
  --text-secondary: #9aa6bd;
  --text-muted: #647089;
  --accent-primary: #5b8dff;

  /* Light canvas (graph background) */
  --canvas-bg: #f7f8fa;
  
  /* Node colors */
  --node-service: #5b8dff;
  --node-topic: #b15bff;
  --node-route: #22b8b0;
  --node-file: #ffb240;
  --node-function: #4cc97c;
  --node-identifier: #ff6f91;

  /* Status */
  --status-ok: #3ddc84;
  --status-warn: #ffc857;
  --status-error: #ff5d5d;
}
```

---

## Component Details

### App.tsx
- Two pages: "graph" and "analyst"
- Graph page has IconRail, CommandBar, Drawers
- Analyst page spans full width

### ImpactAnalyst.tsx (main pipeline UI)
States:
- `isGathering`: Show chat conversation
- `isRequirementsReady`: Show requirements summary + confirm button
- `isProcessing`: Show loading screen with spinner
- `isAwaitingApproval`: Show report + approve/reject
- `isComplete`: Show success/failure message

### types.ts - Key Types
```typescript
type PipelineStage = 
  | "gathering"
  | "requirements_ready"
  | "analyzing"
  | "verifying"
  | "filling_gaps"
  | "awaiting_approval"
  | "approved"
  | "rejected"
  | "failed";

interface PipelineState {
  id: string;
  stage: PipelineStage;
  requirements?: PipelineRequirements;
  conversation_history?: ChatMessage[];
  current_question?: string | null;
  report?: string | null;
  verification?: { complete, confidence, gaps, verified_paths };
  iteration?: number;
  max_iterations?: number;
}
```

---

## Redesign Candidates

1. **Unified view**: Graph + chat in same view, not separate tabs
2. **Report visualization**: Render layers as a tree/graph, not text
3. **Real-time updates**: WebSocket for pipeline progress
4. **Service validation**: Reject non-existent services from LLM
5. **Diff view**: Show what would change in each file
6. **Task tracking**: Checkbox list for generated tasks
7. **History**: View past analyses
8. **Export**: Download report as PDF/markdown

---

## Files to Delete on Redesign

If starting fresh, these can be removed:
- `components/IngestPanel.tsx` - Ingest not used in Forge
- `components/ResultsDrawer.tsx` - Legacy GRACE results
- `components/CommandBar.tsx` - If merging into unified UI
- `graph/useBlastRadius.ts` - Legacy query hook
- Most of `index.css` - Start fresh with Tailwind or CSS modules
