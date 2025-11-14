import { createContext, useState, ReactNode, useEffect } from 'react';
import * as api from '../api';
import { Project, User, AuthPayload } from '../types';

export interface AppContextType {
  isAuthenticated: boolean;
  user: User | null;
  isLoading: boolean;
  projects: Project[];
  currentProject: Project | null;
  setCurrentProject: (project: Project | null) => void;
  login: (payload: AuthPayload) => Promise<void>;
  logout: () => Promise<void>;
}

export const AppContext = createContext<AppContextType | undefined>(undefined);

export const AppProvider = ({ children }: { children: ReactNode }) => {
  // --- Auth State ---
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // --- App State ---
  const [projects, setProjects] = useState<Project[]>([]);
  const [currentProject, setCurrentProject] = useState<Project | null>(null);

  // --- Effect: Check auth on app load ---
  useEffect(() => {
    const checkUserStatus = async () => {
      try {
        const userData = await api.checkAuth();
        setUser(userData);
        setIsAuthenticated(true);

        // Load projects after auth check
        try {
          const projectsData = await api.getProjects();
          setProjects(projectsData.projects || []);
        } catch (err) {
          console.error('Failed to load projects:', err);
        }
      } catch (error) {
        setUser(null);
        setIsAuthenticated(false);
      } finally {
        setIsLoading(false);
      }
    };

    checkUserStatus();
  }, []);

  // --- Auth Functions ---
  const login = async (payload: AuthPayload) => {
    try {
      const userData = await api.login(payload);
      setUser(userData);
      setIsAuthenticated(true);

      // Load projects after login
      try {
        const projectsData = await api.getProjects();
        setProjects(projectsData.projects || []);
      } catch (err) {
        console.error('Failed to load projects:', err);
      }
    } catch (error) {
      setIsAuthenticated(false);
      setUser(null);
      throw error;
    }
  };

  const logout = async () => {
    try {
      await api.logout();
    } finally {
      setUser(null);
      setIsAuthenticated(false);
      setProjects([]);
      setCurrentProject(null);
    }
  };

  return (
    <AppContext.Provider
      value={{
        isAuthenticated,
        user,
        isLoading,
        projects,
        currentProject,
        setCurrentProject,
        login,
        logout,
      }}
    >
      {children}
    </AppContext.Provider>
  );
};
