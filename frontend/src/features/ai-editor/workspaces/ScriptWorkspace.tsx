
import React from 'react';
import { ScriptIcon } from '../components/icons';

const ScriptWorkspace: React.FC<{ onOpenProject?: () => void }> = ({ onOpenProject }) => {
    return (
        <div className="studio-workspace flex flex-col items-center justify-center h-full text-gray-500">
            <ScriptIcon className="w-16 h-16 mb-4 text-gray-700"/>
            <h2 className="text-xl font-semibold">Script Workspace</h2>
            <p>Please use the "Project" tab for the integrated script and production workflow.</p>
            <button className="app-button mt-4" onClick={onOpenProject}>Open Project workflow</button>
        </div>
    );
};

export default ScriptWorkspace;
