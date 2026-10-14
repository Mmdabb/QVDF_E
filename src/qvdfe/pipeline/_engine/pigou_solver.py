"""Wardrop and system-optimum solver methods for parallel-route assignment."""
import numpy as np
from scipy.optimize import brentq, minimize_scalar

POLS = ["CO2", "NOx", "CO", "HC"]

class PigouNetwork:
    def costs(self, y, kind='time', eta=0.):
        z = self.state(y)
        if kind == 'time':
            return z['T'], z['dT'], self.T2
        if kind == 'generalized':
            k = eta*self.emission_scale
            return z['T']+k*z['e_CO2'], z['dT']+k*z['de_CO2'], self.T2+k*self.e2['CO2']
        assert kind in POLS
        return z['e_'+kind], z['de_'+kind], self.e2[kind]


    def private_gap(self, y, kind, eta=0.):
        c1, _, c2 = self.costs(y, kind, eta)
        return c1-c2


    def objective(self, y, kind, eta=0.):
        c1, _, c2 = self.costs(y, kind, eta)
        return (self.B+np.asarray(y))*c1 + (self.N-np.asarray(y))*c2


    def derivative(self, y, kind, eta=0.):
        c1, dc1, c2 = self.costs(y, kind, eta)
        return c1+(self.B+np.asarray(y))*dc1-c2


    def roots(self, function, grid_size=10001):
        grid = np.linspace(0, self.N, grid_size)
        values = np.asarray(function(grid), float)
        candidates = list(grid[np.abs(values) < 1e-12])
        for i in np.flatnonzero(values[:-1]*values[1:] < 0):
            candidates.append(brentq(function, grid[i], grid[i+1], xtol=1e-10, rtol=1e-13))
        return sorted({round(float(x), 8) for x in candidates})


    def equilibria(self, kind, eta=0., grid_size=10001):
        fun = lambda y: self.private_gap(y, kind, eta)
        candidates = self.roots(fun, grid_size)
        if fun(0.) >= -1e-12:
            candidates.append(0.)
        if fun(self.N) <= 1e-12:
            candidates.append(self.N)
        out = sorted(set(candidates))
        assert out, (kind, eta, 'no equilibrium found')
        return out


    def optimum(self, kind, eta=0., grid_size=10001):
        candidates = [0., self.N] + self.roots(lambda y: self.derivative(y, kind, eta), grid_size)
        grid = np.linspace(0, self.N, grid_size)
        obj = self.objective(grid, kind, eta)
        # Independent local brackets supplement the analytic stationary roots.
        for i in np.flatnonzero((obj[1:-1] <= obj[:-2]) & (obj[1:-1] <= obj[2:]))+1:
            res = minimize_scalar(lambda y: self.objective(y, kind, eta), bounds=(grid[i-1], grid[i+1]),
                                  method='bounded', options={'xatol': 1e-9})
            candidates.append(float(res.x))
        best = min(candidates, key=lambda y: self.objective(y, kind, eta))
        assert self.objective(best, kind, eta) <= obj.min()+1e-8*max(1., obj.min())
        return float(best), float(self.objective(best, kind, eta))


    def outcome(self, label, y, eta=None):
        z = self.state(y)
        result = dict(assignment=label, eta=eta, flexible_route1_share=y/self.N,
                      flexible_route1_veh=y, background_veh=self.B, flexible_demand_veh=self.N,
                      route1_total_veh=self.B+y, route2_total_veh=self.N-y,
                      x_h=float(z['x']), vq_mph=float(z['vq']), P_h=float(z['P']),
                      travel_time_veh_h=float(self.objective(y, 'time')))
        for poll in POLS:
            result[poll+'_g'] = float(self.objective(y, poll))
        return result
