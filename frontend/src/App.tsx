import { Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Overview from './pages/Overview';
import Transactions from './pages/Transactions';
import TransactionDetail from './pages/TransactionDetail';
import RecoveryQueue from './pages/RecoveryQueue';
import AgentReplay from './pages/AgentReplay';
import PolicyCenter from './pages/PolicyCenter';
import ExperimentLab from './pages/ExperimentLab';

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Overview />} />
        <Route path="/transactions" element={<Transactions />} />
        <Route path="/transactions/:transactionId" element={<TransactionDetail />} />
        <Route path="/recovery-queue" element={<RecoveryQueue />} />
        <Route path="/agent-replay" element={<AgentReplay />} />
        <Route path="/agent-replay/:transactionId" element={<AgentReplay />} />
        <Route path="/policy-center" element={<PolicyCenter />} />
        <Route path="/experiment-lab" element={<ExperimentLab />} />
      </Routes>
    </Layout>
  );
}
