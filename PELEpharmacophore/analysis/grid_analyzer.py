import os
import copy
import numpy as np
from scipy.spatial import distance
from functools import reduce
import PELEpharmacophore.helpers as hl
import PELEpharmacophore.analysis.grid as gr
import PELEpharmacophore.analysis.simulation_analyzer as sa

class GridAnalyzer(sa.SimulationAnalyzer):
    """
    Class for analysing PELE simulations using a grid.
    """

    def set_grid(self, center, radius):
        """
        Set the grid .

        Parameters
        ----------
        center : list
            xyz coordinates of the grid center.
        radius : int
            Length of half the side of the grid.
        """
        self.grid = gr.Grid(center, radius)
        self.grid.generate_voxels()


    def get_grid_atoms(self, coords):
        """
        Gets all the atoms inside the grid for a given model.

        Parameters
        ----------
        model : Bio.PDB.Model
            Biopython model object.

        Returns
        ----------
        featured_grid_atoms : list of Atom objects
            Atoms inside the grid.
        """
        dist = np.sqrt(3)*self.grid.radius #get dist from center to vertex
        atoms_near = hl.neighbor_search(coordinates, self.grid.center, dist)
        inside_grid_mask = np.logical_and(self.grid.v1 <= a, a <=  self.grid.v8).all(axis=1)
        grid_atoms = coords[inside_grid_mask]
        return grid_atoms


    def check_voxels(self, coords):
        """
        Check which atoms are inside which voxel of the grid.

        Parameters
        ----------
        grid_atoms : list of Atom objects
            Atoms inside the grid.

        Returns
        ----------
        model_grid : Grid object
            Grid object that contains the given atoms in the correspondent voxels.
        """
        model_grid = copy.deepcopy(self.grid)
        voxel_centers = np.array([v.center for v in model_grid.voxels])
        dist = distance.cdist(coords, voxel_centers, 'sqeuclidean')
        voxel_inds = dist.argmin(axis=1) #get index of closest voxel to each atom
        return voxel_inds


    def fill_grid(self, feature, voxel_inds):
        for i in voxel_inds:
            self.grid.voxels[voxel].count_feature(feature)


    def merge_grids(self, grid, other_grid):
        """
        Merge the information from two grids together.

        Parameters
        ----------
        grid, other_grid : Grid object
            Grids to merge.

        Returns
        ----------
        grid : Grid object
            Merged grid.
        """
        if grid.is_empty():
            grid = copy.deepcopy(other_grid)
        else:
            for i, other_voxel in enumerate(other_grid.voxels):
                voxel = grid.voxels[i]
                if other_voxel.freq_dict:
                    for feature, other_freq in other_voxel.freq_dict.items():
                        voxel.freq_dict = hl.frequency_dict(voxel.freq_dict, feature, other_freq)
                        other_models = other_voxel.origin_dict[feature]
                        for model in other_models:
                            voxel.origin_dict = hl.list_dict(voxel.origin_dict, feature, model)
        return grid


    def analyze_trajectory(self, traj_and_report):
        """
        Analyze a given trajectory file.
        The analysis consist in, for each of the models in the trajectory,
        getting the atoms inside the grid and checking the voxels.

        Parameters
        ----------
        traj_and_report : tuple
            Trajectory and its respective report.

        Returns
        ----------
        traj_grid : Grid object
            Grid that contains the atoms for all the models in the trajectory.
        """
        trajfile, report = traj_and_report
        trajectory = self.get_structure(trajfile)
        accepted_steps = hl.accepted_pele_steps(report)
        traj_grid = copy.deepcopy(self.grid)
        for step in accepted_steps:
            model = trajectory[step]
            grid_atoms = self.get_grid_atoms(model)
            if grid_atoms:
                model_grid = self.check_voxels(grid_atoms)
                traj_grid = self.merge_grids(traj_grid, model_grid)
        return traj_grid


    def run(self, ncpus):
        """
        Analyze the full simulation.

        Parameters
        ----------
        ncpus : int
            Number of processors.
        """
        indices = self.get_indices()

        coord_dicts = hl.parallelize(self.get_coordinates, trajectory, indices, ncpus)

        merged_coord_dict = hl.merge_array_dicts(*coord_dicts)

        grid_atoms_dict = {}
        for feature, coords in merged_coord_dict:
            grid_atoms_dict[feature] = self.get_grid_atoms(coords)

        voxel_ind_dict = {}
        for feature, coords in grid_atoms_dict:
            voxel_ind_dict[feature] = self.check_voxels(coords)

        for feature, inds in voxel_ind_dict:
            self.fill_grid(feature, inds)

    def set_frequency_filter(self, threshold):
        """
        Set a threshold to not show voxels with lower frequencies.
        For each feature, it creates a histogram of 10 bins with the frequencies of each voxel.

        Parameters
        ----------
        threshold : int
            Number of the bins that won't be saved.
            E. g.: if it's 1, the voxels on the first bin of the histogram won't be saved.
        """
        freq_dict_all = {}
        self.threshold_dict = {}
        for voxel in self.grid.voxels:
            if voxel.freq_dict:
                for feature, freq in voxel.freq_dict.items():
                    freq_dict_all = hl.list_dict(freq_dict_all, feature, freq)
        for element, freqlist in freq_dict_all.items():
            hist, bin_edges = np.histogram(freqlist)
            self.threshold_dict[element] = bin_edges[threshold]
        return self.threshold_dict

    def save_pharmacophores(self, outdir="Pharmacophores"):
        """
        Save pharmacophore files in PDB format.

        Parameters
        ----------
        outdir : str
            Directory with the results.
        """
        if not os.path.isdir(outdir):
            os.mkdir(outdir)
        for feature in self.threshold_dict:
            path = os.path.join(outdir, f"{feature}pharmacophore.pdb")
            f = open(path, 'w')
            f.close()
        for voxel in self.grid.voxels:
            if voxel.freq_dict:
                for feature, freq in voxel.freq_dict.items():
                    path = os.path.join(outdir, f"{feature}pharmacophore.pdb")
                    if freq >= self.threshold_dict[feature]:
                        with open(path, 'a') as f:
                            feature_origin = voxel.origin_dict[feature]
                            f.write(hl.format_line_pdb(voxel.center, feature, freq, feature_origin))

if __name__ == "__main__":
    target = GridAnalyzer("/gpfs/scratch/bsc72/bsc72801/ana_sanchez/test1_frag82")
    #target = GridAnalizer("PELEpharmacophore/1/")
    target.set_ligand("L", "FRA", 900)
    #features={'HBD': ['NC1'], 'HBA': ['NB1', 'NC3', 'O2'], 'ALI': ['FD3', 'C1'], 'ARO': ['CA5', 'CD1']}
    #features={'NEG': ['C2'], 'ALI': ['C1']}
    features = {'ARO':['C5']}
    target.set_features(features)
    target.set_grid((2.173, 15.561, 28.257), 7)
    target.run(23)
    target.set_frequency_filter(0)
    target.save_pharmacophores("PharmacophoresTest1_frag82")
