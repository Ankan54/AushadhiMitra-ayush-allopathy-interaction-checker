# Frontend Steering File - AushadhiMitra

## Purpose
React-based web interface with dual UX: professional UI with interactive knowledge graph for AYUSH practitioners, and simple chat interface for patients.

## Architecture
- **Framework**: React 18+ with TypeScript
- **State Management**: React Context API or Redux
- **WebSocket**: Real-time agent trace streaming
- **Graph Visualization**: Cytoscape.js for knowledge graph
- **Styling**: Tailwind CSS or Material-UI
- **Build**: Vite or Create React App

## User Personas

### 1. Professional User (AYUSH Practitioner)
**Needs**: Detailed technical information, visual knowledge graph, source citations

**UI Components**:
- Medicine input form (AYUSH + Allopathic)
- Real-time execution trace panel
- Interactive Cytoscape.js knowledge graph
- Severity badge with score breakdown
- Detailed comparison table (AYUSH profile vs Allopathy profile)
- Mechanism explanation cards (CYP pathway, pharmacodynamic)
- Clickable source citations (PubMed, DrugBank, IMPPAT)
- Conflict indicator (when evidence disagrees)
- Medical disclaimer

### 2. Patient User
**Needs**: Simple conversational interface, multilingual support, clear actionable advice

**UI Components**:
- Chat interface (WhatsApp-like)
- Message bubbles (user + AI)
- Language detection (Hindi, English, Hinglish)
- Severity indicator (color-coded: green/yellow/orange/red)
- Simple action recommendations
- "Consult doctor" prompt for MODERATE/MAJOR severity

## Key Features

### WebSocket Integration
```typescript
// Connect to WebSocket
const ws = new WebSocket('ws://localhost:8000/ws/check-interaction');

// Send query
ws.send(JSON.stringify({
  ayush_medicine: "turmeric",
  allopathy_drug: "warfarin",
  user_type: "professional"
}));

// Receive events
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  switch(data.type) {
    case 'status':
      // Update status indicator
      break;
    case 'trace':
      // Append to trace log
      break;
    case 'agent_complete':
      // Mark agent as complete
      break;
    case 'validation':
      // Show validation status
      break;
    case 'response_chunk':
      // Stream response text
      break;
    case 'complete':
      // Render final response
      break;
  }
};
```

### Knowledge Graph Rendering (Cytoscape.js)
```typescript
import cytoscape from 'cytoscape';

const renderKnowledgeGraph = (graphData: KnowledgeGraph) => {
  const cy = cytoscape({
    container: document.getElementById('cy'),
    
    elements: {
      nodes: graphData.nodes.map(node => ({
        data: {
          id: node.id,
          label: node.label,
          type: node.type,
          isOverlap: node.is_overlap || false
        }
      })),
      edges: graphData.edges.map(edge => ({
        data: {
          source: edge.source,
          target: edge.target,
          label: edge.relationship
        }
      }))
    },
    
    style: [
      {
        selector: 'node[type="Plant"]',
        style: { 'background-color': '#4CAF50' }
      },
      {
        selector: 'node[type="Drug"]',
        style: { 'background-color': '#2196F3' }
      },
      {
        selector: 'node[type="CYP_Enzyme"]',
        style: { 'background-color': '#FF9800' }
      },
      {
        selector: 'node[isOverlap]',
        style: { 'border-width': 3, 'border-color': '#F44336' }
      },
      {
        selector: 'edge[relationship="INHIBITS"]',
        style: { 'line-color': '#F44336', 'target-arrow-color': '#F44336' }
      },
      {
        selector: 'edge[relationship="METABOLIZED_BY"]',
        style: { 'line-color': '#2196F3', 'target-arrow-color': '#2196F3' }
      }
    ],
    
    layout: {
      name: 'cose',
      animate: true
    }
  });
};
```

### Severity Badge Component
```typescript
interface SeverityBadgeProps {
  severity: 'NONE' | 'MINOR' | 'MODERATE' | 'MAJOR';
  score: number;
  factors: string[];
}

const SeverityBadge: React.FC<SeverityBadgeProps> = ({ severity, score, factors }) => {
  const colorMap = {
    NONE: 'bg-green-500',
    MINOR: 'bg-yellow-500',
    MODERATE: 'bg-orange-500',
    MAJOR: 'bg-red-500'
  };
  
  return (
    <div className={`${colorMap[severity]} text-white p-4 rounded-lg`}>
      <h3 className="text-xl font-bold">{severity}</h3>
      <p className="text-sm">Score: {score}/100</p>
      <ul className="mt-2 text-xs">
        {factors.map((factor, i) => (
          <li key={i}>• {factor}</li>
        ))}
      </ul>
    </div>
  );
};
```

### Source Citation Component
```typescript
interface SourceProps {
  url: string;
  title: string;
  category: 'PubMed' | 'DrugBank' | 'FDA' | 'research_paper' | 'general';
}

const SourceCitation: React.FC<SourceProps> = ({ url, title, category }) => {
  const iconMap = {
    PubMed: '📚',
    DrugBank: '💊',
    FDA: '🏛️',
    research_paper: '📄',
    general: '🔗'
  };
  
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" 
       className="flex items-center gap-2 p-2 hover:bg-gray-100 rounded">
      <span>{iconMap[category]}</span>
      <span className="text-blue-600 underline">{title}</span>
    </a>
  );
};
```

## Page Structure

### Professional UI Layout
```
┌─────────────────────────────────────────────────────────┐
│ Header: AushadhiMitra Logo | Mode: Professional         │
├─────────────────────────────────────────────────────────┤
│ Input Form                                              │
│  ┌─────────────────┐  ┌─────────────────┐             │
│  │ AYUSH Medicine  │  │ Allopathic Drug │  [Check]    │
│  └─────────────────┘  └─────────────────┘             │
├─────────────────────────────────────────────────────────┤
│ Execution Trace (collapsible)                          │
│  • PlannerAgent: Identifying substances...             │
│  • AYUSHAgent: Looking up IMPPAT data...               │
│  • AllopathyAgent: Web search in progress...           │
│  • ReasoningAgent: Building knowledge graph...         │
│  • Validation: PASSED (1 iteration)                    │
├─────────────────────────────────────────────────────────┤
│ ┌─────────────────┐  ┌─────────────────────────────┐  │
│ │ Severity Badge  │  │ Knowledge Graph (Cytoscape) │  │
│ │  MAJOR          │  │                             │  │
│ │  Score: 75/100  │  │   [Interactive Graph]       │  │
│ │  • CYP2C9       │  │                             │  │
│ │  • NTI drug     │  │                             │  │
│ └─────────────────┘  └─────────────────────────────┘  │
├─────────────────────────────────────────────────────────┤
│ Interaction Mechanisms                                  │
│  ┌─────────────────────────────────────────────────┐   │
│  │ CYP2C9 Pathway                                  │   │
│  │ Curcumin inhibits CYP2C9; Warfarin is CYP2C9   │   │
│  │ substrate → elevated Warfarin levels → bleeding │   │
│  └─────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────┤
│ Detailed Profiles                                       │
│  ┌──────────────────┐  ┌──────────────────┐           │
│  │ AYUSH Profile    │  │ Allopathy Profile│           │
│  │ Curcuma longa    │  │ Warfarin         │           │
│  │ • Curcumin       │  │ • NTI drug       │           │
│  │ • CYP2C9 inhib.  │  │ • CYP2C9 substr. │           │
│  └──────────────────┘  └──────────────────┘           │
├─────────────────────────────────────────────────────────┤
│ Research Citations                                      │
│  📚 PubMed: Curcumin-warfarin interaction...           │
│  💊 DrugBank: Warfarin metabolism...                   │
│  📄 IMPPAT: Curcuma longa phytochemicals...            │
├─────────────────────────────────────────────────────────┤
│ ⚠️ Disclaimer: This tool provides informational        │
│    analysis only. Consult a healthcare professional.   │
└─────────────────────────────────────────────────────────┘
```

### Patient Chat UI Layout
```
┌─────────────────────────────────────────────────────────┐
│ Header: AushadhiMitra | Chat Mode                      │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ User: I'm taking turmeric and warfarin          │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ AI: ⚠️ MAJOR Interaction Detected               │   │
│  │                                                 │   │
│  │ Turmeric (haldi) can significantly increase    │   │
│  │ the blood-thinning effect of Warfarin. This    │   │
│  │ may lead to excessive bleeding. Please consult │   │
│  │ your doctor before continuing both medicines.  │   │
│  │                                                 │   │
│  │ [View Details] [Consult Doctor]                │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
├─────────────────────────────────────────────────────────┤
│ [Type your message...]                      [Send]     │
└─────────────────────────────────────────────────────────┘
```

## State Management

### Context Structure
```typescript
interface AppState {
  // User settings
  userType: 'professional' | 'patient';
  language: 'en' | 'hi' | 'hinglish';
  
  // Query state
  ayushMedicine: string;
  allopathyDrug: string;
  isLoading: boolean;
  
  // Execution trace
  traces: TraceEvent[];
  currentAgent: string | null;
  loopIterations: number;
  validationStatus: 'PASSED' | 'NEEDS_MORE_DATA' | null;
  
  // Response data
  response: InteractionResponse | null;
  knowledgeGraph: KnowledgeGraph | null;
  severity: SeverityData | null;
  
  // Error handling
  error: string | null;
  executionMode: 'flow' | 'pipeline' | null;
}
```

## API Integration

### REST Endpoints
```typescript
// Health check
GET /api/health
Response: {
  status: "healthy",
  agents: { planner: "...", ayush: "...", allopathy: "...", reasoning: "..." },
  flow_id: "...",
  database: "connected"
}

// Synchronous check
POST /api/check-interaction
Body: { ayush_medicine: "...", allopathy_drug: "...", user_type: "..." }
Response: { ... full interaction response ... }

// List curated interactions
GET /api/interactions
Response: [{ interaction_key: "...", severity: "...", ... }]
```

### WebSocket Events
```typescript
type WebSocketEvent = 
  | { type: 'status', message: string }
  | { type: 'trace', message: string, data?: any }
  | { type: 'agent_complete', message: string }
  | { type: 'validation', message: string, loop_iterations: number }
  | { type: 'response_chunk', message: string }
  | { type: 'complete', full_response: any, execution_mode: string, loop_iterations: number };
```

## Multilingual Support

### Language Detection
```typescript
const detectLanguage = (text: string): 'en' | 'hi' | 'hinglish' => {
  const hindiChars = /[\u0900-\u097F]/;
  const englishChars = /[a-zA-Z]/;
  
  const hasHindi = hindiChars.test(text);
  const hasEnglish = englishChars.test(text);
  
  if (hasHindi && hasEnglish) return 'hinglish';
  if (hasHindi) return 'hi';
  return 'en';
};
```

### Response Formatting
- Professional users: Always English with technical terms
- Patient users: Match input language (Hindi/English/Hinglish)
- Severity labels: Translated (MAJOR → गंभीर)
- Action recommendations: Localized

## Testing Priorities

1. **WebSocket Connection**: Reconnect on disconnect, handle timeout
2. **Knowledge Graph Rendering**: Handle empty/partial graphs gracefully
3. **Severity Badge**: Correct color mapping for all levels
4. **Source Citations**: All URLs clickable and open in new tab
5. **Responsive Design**: Mobile-friendly chat interface
6. **Language Detection**: Accurate Hindi/English/Hinglish detection
7. **Error States**: Display user-friendly error messages
8. **Loading States**: Show progress during agent execution
9. **Trace Streaming**: Real-time updates without UI lag

## Deployment

### Build Configuration
```json
// package.json
{
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "cytoscape": "^3.26.0",
    "cytoscape-cose-bilkent": "^4.1.0"
  }
}
```

### Static File Serving
- Build output: `frontend/dist/`
- Served by: FastAPI `GET /` endpoint
- Nginx: Reverse proxy + static file caching

### Environment Variables
```
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
```

## Accessibility

- Keyboard navigation for all interactive elements
- ARIA labels for graph nodes and edges
- Screen reader support for severity announcements
- High contrast mode for severity badges
- Focus indicators for form inputs

## Performance Optimization

- Lazy load Cytoscape.js (code splitting)
- Debounce medicine input (avoid excessive API calls)
- Memoize knowledge graph rendering
- Virtual scrolling for trace log (if >100 events)
- WebSocket message batching (avoid UI thrashing)
