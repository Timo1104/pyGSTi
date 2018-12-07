""" Defines the LocalNoiseModel class and supporting functions """
from __future__ import division, print_function, absolute_import, unicode_literals
#*****************************************************************
#    pyGSTi 0.9:  Copyright 2015 Sandia Corporation
#    This Software is released under the GPL license detailed
#    in the file "license.txt" in the top-level pyGSTi directory
#*****************************************************************

import numpy as _np
import copy as _copy
import itertools as _itertools
import collections as _collections
import scipy.sparse as _sps
import warnings as _warnings

from . import model as _mdl
from . import operation as _op
from . import spamvec as _sv
from . import povm as _povm
from . import qubitgraph as _qgraph
from ..tools import optools as _gt
from ..tools import basistools as _bt
from ..tools import internalgates as _itgs

from ..baseobjs import VerbosityPrinter as _VerbosityPrinter
from ..baseobjs import Basis as _Basis
from ..baseobjs import Dim as _Dim
from ..baseobjs import Label as _Lbl

from ..baseobjs.basisconstructors import sqrt2, id2x2, sigmax, sigmay, sigmaz

# TODO docstrings -- at least check them in this (new) module
class LocalNoiseModel(_mdl.ImplicitOpModel):
    """ 
    A n-qubit model by embedding the *same* gates from `gatedict`
    as requested and creating a perfect 0-prep and z-basis POVM.
    """

    @classmethod
    def build_standard(cls, nQubits, gate_names, nonstd_gate_unitaries={}, availability={}, 
                       qubit_labels=None, geometry="line", parameterization='static',
                       evotype="auto", sim_type="auto", on_construction_error='raise',
                       independent_gates=False, ensure_composed_gates=True):
        """
        TODO: docstring - add geometry
        Creates a "standard" n-qubit model, usually of ideal gates.
    
        The returned model is "standard", in that the following standard gate
        names may be specified as elements to `gate_names` without the need to
        supply their corresponding unitaries (as one must when calling
        the constructor directly):
    
        - 'Gi' : the 1Q idle operation
        - 'Gx','Gy','Gz' : 1Q pi/2 rotations
        - 'Gxpi','Gypi','Gzpi' : 1Q pi rotations
        - 'Gh' : Hadamard
        - 'Gp' : phase
        - 'Gcphase','Gcnot','Gswap' : standard 2Q gates
    
        Furthermore, if additional "non-standard" gates are needed,
        they are specified by their *unitary* gate action, even if
        the final model propagates density matrices (as opposed
        to state vectors).
    
        Parameters
        ----------
        nQubits : int
            The total number of qubits.
    
        gate_names : list
            A list of string-type gate names (e.g. `"Gx"`) either taken from
            the list of builtin "standard" gate names given above or from the
            keys of `nonstd_gate_unitaries`.  These are the typically 1- and 2-qubit
            gates that are repeatedly embedded (based on `availability`) to form
            the resulting model.
    
        nonstd_gate_unitaries : dict, optional 
            A dictionary of numpy arrays which specifies the unitary gate action
            of the gate names given by the dictionary's keys.
    
        availability : dict, optional
            A dictionary whose keys are gate names and whose values are lists of 
            qubit-label-tuples.  See constructor docstring for more details.
    
        parameterization : {"full", "TP", "CPTP", "H+S", "S", "static", "H+S terms",
                            "H+S clifford terms", "clifford"}
            The type of parameterizaton to use for each gate value before it is
            embedded. See :method:`Model.set_all_parameterizations` for more
            details.
    
        evotype : {"auto","densitymx","statevec","stabilizer","svterm","cterm"}
            The evolution type.  Often this is determined by the choice of 
            `parameterization` and can be left as `"auto"`, which prefers
            `"densitymx"` (full density matrix evolution) when possible. In some
            cases, however, you may want to specify this manually.  For instance,
            if you give unitary maps instead of superoperators in `gatedict`
            you'll want to set this to `"statevec"`.
    
        sim_type : {"auto", "matrix", "map", "termorder:<N>"} 
            The simulation method used to compute predicted probabilities for the
            resulting :class:`Model`.  Usually `"auto"` is fine, the default for
            each `evotype` is usually what you want.  Setting this to something
            else is expert-level tuning.
    
        on_construction_error : {'raise','warn',ignore'}
            What to do when the creation of a gate with the given 
            `parameterization` fails.  Usually you'll want to `"raise"` the error.
            In some cases, for example when converting as many gates as you can
            into `parameterization="clifford"` gates, `"warn"` or even `"ignore"`
            may be useful.
    
        Returns
        -------
        Model
            A model with `"rho0"` prep, `"Mdefault"` POVM, and gates labeled by
            gate name (keys of `gatedict`) and qubit labels (from within
            `availability`).  For instance, the operation label for the `"Gx"` gate on
            qubit 2 might be `Label("Gx",1)`.
        """
        std_unitaries = _itgs.get_standard_gatename_unitaries()
    
        if evotype == "auto": # same logic as in LocalNoiseModel
            if parameterization == "clifford": evotype = "stabilizer"
            elif parameterization == "H+S terms": evotype = "svterm"
            elif parameterization == "H+S clifford terms": evotype = "cterm"
            else: evotype = "densitymx" #everything else
        
        gatedict = _collections.OrderedDict()
        for name in gate_names:
            #TODO REMOVE
            #if name == "Gi": # special case: Gi as a gate *name* is interpreted as a
            #    gatedict[name] = "PerfectIdle" # perfect idle operation/placeholder.
            #    continue
                
            U = nonstd_gate_unitaries.get(name, std_unitaries.get(name,None))
            if U is None: raise KeyError("'%s' gate unitary needs to be provided by `nonstd_gate_unitaries` arg" % name)
            if evotype in ("densitymx","svterm","cterm"): 
                gatedict[name] = _bt.change_basis(_gt.unitary_to_process_mx(U), "std", "pp")
            else: #we just store the unitaries
                assert(evotype in ("statevec","stabilizer")), "Invalid evotype: %s" % evotype
                gatedict[name] = U

        return cls(nQubits, gatedict, availability, qubit_labels,
                   geometry, parameterization, evotype,
                   sim_type, on_construction_error,
                   independent_gates, ensure_composed_gates)


    def __init__(self, nQubits, gatedict, availability=None, qubit_labels=None,
                 geometry="line", parameterization='static', evotype="auto",
                 sim_type="auto", on_construction_error='raise',
                 independent_gates=False, ensure_composed_gates=True):
        """
        Creates a n-qubit model by embedding the *same* gates from `gatedict`
        as requested and creating a perfect 0-prep and z-basis POVM.
    
        The gates in `gatedict` often act on fewer (typically just 1 or 2) than
        the total `nQubits` qubits, in which case embedded-gate objects are
        automatically (and repeatedly) created to wrap the lower-dimensional gate.
        Parameterization of each gate is done once, before any embedding, so that 
        just a single set of parameters will exist for each low-dimensional gate.
        
        Parameters
        ----------
        nQubits : int
            The total number of qubits.
    
        gatedict : dict
            A dictionary (an `OrderedDict` if you care about insertion order) which 
            associates with string-type gate names (e.g. `"Gx"`) :class:`LinearOperator`,
            `numpy.ndarray` objects. When the objects may act on fewer than the total
            number of qubits (determined by their dimension/shape) then they are
            repeatedly embedded into `nQubits`-qubit gates as specified by `availability`.
          
        availability : dict, optional
            A dictionary whose keys are the same gate names as in
            `gatedict` and whose values are lists of qubit-label-tuples.  Each
            qubit-label-tuple must have length equal to the number of qubits
            the corresponding gate acts upon, and causes that gate to be
            embedded to act on the specified qubits.  For example,
            `{ 'Gx': [(0,),(1,),(2,)], 'Gcnot': [(0,1),(1,2)] }` would cause
            the `1-qubit `'Gx'`-gate to be embedded three times, acting on qubits
            0, 1, and 2, and the 2-qubit `'Gcnot'`-gate to be embedded twice,
            acting on qubits 0 & 1 and 1 & 2.  Instead of a list of tuples,
            values of `availability` may take the special values 
            `"all-permutations"` and `"all-combinations"`, which as their names
            imply, equate to all possible permutations and combinations of the 
            appropriate number of qubit labels (deterined by the gate's dimension).
            If a gate name (a key of `gatedict`) is not present in `availability`,
            the default is `"all-permutations"`.
    
        parameterization : {"full", "TP", "CPTP", "H+S", "S", "static", "H+S terms",
                            "H+S clifford terms", "clifford"}
            The type of parameterizaton to convert each value in `gatedict` to. See
            :method:`Model.set_all_parameterizations` for more details.
    
        evotype : {"auto","densitymx","statevec","stabilizer","svterm","cterm"}
            The evolution type.  Often this is determined by the choice of 
            `parameterization` and can be left as `"auto"`, which prefers
            `"densitymx"` (full density matrix evolution) when possible. In some
            cases, however, you may want to specify this manually.  For instance,
            if you give unitary maps instead of superoperators in `gatedict`
            you'll want to set this to `"statevec"`.
    
        sim_type : {"auto", "matrix", "map", "termorder:<N>"} 
            The simulation method used to compute predicted probabilities for the
            resulting :class:`Model`.  Usually `"auto"` is fine, the default for
            each `evotype` is usually what you want.  Setting this to something
            else is expert-level tuning.
    
        on_construction_error : {'raise','warn',ignore'}
            What to do when the conversion from a value in `gatedict` to a
            :class:`LinearOperator` of the type given by `parameterization` fails.
            Usually you'll want to `"raise"` the error.  In some cases,
            for example when converting as many gates as you can into
            `parameterization="clifford"` gates, `"warn"` or even `"ignore"`
            may be useful.
    
        Returns
        -------
        Model
            A model with `"rho0"` prep, `"Mdefault"` POVM, and gates labeled by
            gate name (keys of `gatedict`) and qubit labels (from within
            `availability`).  For instance, the operation label for the `"Gx"` gate on
            qubit 2 might be `Label("Gx",1)`.
        """
        if qubit_labels is None:
            qubit_labels = tuple(range(nQubits))
        if availability is None:
            availability = {}

        if isinstance(geometry, _qgraph.QubitGraph):
            qubitGraph = geometry
        else:
            qubitGraph = _qgraph.QubitGraph.common_graph(nQubits, geometry, directed=False,
                                                         qubit_labels=qubit_labels)

        self.nQubits = nQubits
        self.gatedict = _collections.OrderedDict(
            [(gn,_np.array(gate)) for gn,gate in gatedict.items()]) # only hold numpy arrays (so copying is clean)
        self.availability = availability
        self.qubit_labels = qubit_labels
        self.geometry = geometry
        self.parameterization = parameterization
        self.independent_gates = independent_gates
                
        if evotype == "auto": # Note: this same logic is repeated in build_standard above
            if parameterization == "clifford": evotype = "stabilizer"
            elif parameterization == "static unitary": evotype = "statevec"
            elif _gt.is_valid_lindblad_paramtype(parameterization):
                _,evotype = _gt.split_lindblad_paramtype(parameterization)
            else: evotype = "densitymx" #everything else
    
        if evotype in ("densitymx","svterm","cterm"):
            from ..construction import basis_build_vector as _basis_build_vector 
            basis1Q = _Basis("pp",2)
            v0 = _basis_build_vector("0", basis1Q)
            v1 = _basis_build_vector("1", basis1Q)
        elif evotype == "statevec":
            basis1Q = None
            v0 = _np.array([[1],[0]],complex)
            v1 = _np.array([[0],[1]],complex)
        else:
            assert(evotype == "stabilizer"), "Invalid evolution type: %s" % evotype
            basis1Q = v0 = v1 = None # then we shouldn't use these
    
        if sim_type == "auto":
            if evotype == "densitymx":
                sim_type = "matrix" if nQubits <= 2 else "map"
            elif evotype == "statevec":
                sim_type = "matrix" if nQubits <= 4 else "map"
            elif evotype == "stabilizer":
                sim_type = "map" # use map as default for stabilizer-type evolutions
            else: assert(False) # should be unreachable

        super(LocalNoiseModel,self).__init__({}, SimpleCompLayerLizard, {}, sim_type=sim_type, evotype=evotype)
        self.dim = 4**nQubits if evotype in ("densitymx","svterm","cterm") else 2**nQubits
        self.set_state_space_labels(qubit_labels)
    
        if parameterization in ("TP","full"): # then make tensor-product spam
            prep_factors = []; povm_factors = []
            for i in range(nQubits):
                prep_factors.append(
                    _sv.convert(_sv.StaticSPAMVec(v0), "TP", basis1Q) )
                povm_factors.append(
                    _povm.convert(_povm.UnconstrainedPOVM( ([
                        ('0',_sv.StaticSPAMVec(v0)),
                        ('1',_sv.StaticSPAMVec(v1))]) ), "TP", basis1Q) )
            
            self.prep_blks['rho0'] = _sv.TensorProdSPAMVec('prep', prep_factors)
            self.povm_blks['Mdefault'] = _povm.TensorProdPOVM(povm_factors)
    
        elif parameterization == "clifford":
            # Clifford object construction is different enough we do it separately
            self.prep_blks['rho0'] = _sv.StabilizerSPAMVec(nQubits) # creates all-0 state by default
            self.povm_blks['Mdefault'] = _povm.ComputationalBasisPOVM(nQubits,'stabilizer')
    
        elif parameterization in ("static","static unitary"):
            #static computational basis
            self.prep_blks['rho0'] = _sv.ComputationalSPAMVec([0]*nQubits, evotype)
            self.povm_blks['Mdefault'] = _povm.ComputationalBasisPOVM(nQubits, evotype)
    
        else:
            # parameterization should be a type amenable to Lindblad
            # create lindblad SPAM ops w/maxWeight == 1 & errcomp_type = 'gates' (HARDCODED for now)
            from . import cloudnoisemodel as _cnm
            maxSpamWeight = 1; sparse = False; errcomp_type = 'gates'; verbosity=0 #HARDCODED
            qubitGraph = _qgraph.QubitGraph.common_graph(nQubits, "line", qubit_labels=qubit_labels)
              # geometry doesn't matter while maxSpamWeight==1
            
            prepPure = _sv.ComputationalSPAMVec([0]*nQubits, evotype)
            prepNoiseMap = _cnm._build_nqn_global_noise(qubitGraph, maxSpamWeight, sparse, sim_type,
                                                      parameterization, errcomp_type, verbosity)
            self.prep_blks['rho0'] = _sv.LindbladSPAMVec(prepPure, prepNoiseMap, "prep")
    
            povmNoiseMap = _cnm._build_nqn_global_noise(qubitGraph, maxSpamWeight, sparse, sim_type, 
                                                      parameterization, errcomp_type, verbosity)
            self.povm_blks['Mdefault'] = _povm.LindbladParameterizedPOVM(povmNoiseMap, None, "pp")

        Composed = _op.ComposedDenseOp if sim_type == "matrix" else _op.ComposedOp
        primitive_ops = []

        for gateName, gate in gatedict.items():
            if ensure_composed_gates and independent_gates == False \
               and not isinstance(gate,Composed):
                #Make a single ComposedDenseOp *here*, which is used
                # in all the embeddings for different target qubits
                gate = Composed([gate]) # to make adding more factors easy
                self.operation_blks[_Lbl(gateName+"_gate")] = cgate
                
            if not isinstance(gate, _op.LinearOperator):
                try:
                    gate = _op.convert(_op.StaticDenseOp(gate), parameterization, "pp")
                except Exception as e:
                    if on_construction_error == 'warn':
                        _warnings.warn("Failed to create %s gate %s. Dropping it." %
                                       (parameterization, gateName))
                    if on_construction_error in ('warn','ignore'): continue
                    else: raise e
    
            gate_nQubits = int(round(_np.log2(gate.dim)/2)) if (evotype in ("densitymx","svterm","cterm")) \
                           else int(round(_np.log2(gate.dim))) # evotype in ("statevec","stabilizer")
            
            availList = self.availability.get(gateName, 'all-edges')
            if availList == 'all-combinations': 
                availList = list(_itertools.combinations(qubit_labels, gate_nQubits))
            elif availList == 'all-permutations': 
                availList = list(_itertools.permutations(qubit_labels, gate_nQubits))
            elif availList == 'all-edges':
                if gate_nQubits == 1:
                    availList = [(i,) for i in qubit_labels]
                elif gate_nQubits == 2:
                    availList = qubitGraph.edges(double_for_undirected=True)
                else:
                    raise NotImplementedError(("I don't know how to place a %d-qubit gate "
                                               "on graph edges yet") % gate_nQubits)
            self.availability[gateName] = tuple(availList)
                
            for inds in availList:
                if ensure_composed_gates and independent_gates:
                    #Make a single ComposedDenseOp *here*, for *only this* embedding
                    cgate = Composed([gate]) # to make adding more factors easy
                    self.operation_blks[_Lbl(gateName+"_gate",inds)] = cgate
                else:
                    cgate = gate # already a Composed operator (for easy addition of factors)
                    
                try:
                    # Note: can't use automatic-embedding b/c we need to force embedding
                    # when just ordering doesn't align (e.g. Gcnot:1:0 on 2-qubits needs to embed)
                    if inds == tuple(qubit_labels):
                        embedded_op = cgate
                    elif sim_type == "matrix":
                        embedded_op = _op.EmbeddedDenseOp(self.stateSpaceLabels, inds, cgate)
                    else: # sim_type == "map" or sim_type.startswidth("termorder"):
                        embedded_op = _op.EmbeddedOp(self.stateSpaceLabels, inds, cgate)
                    self.operation_blks[_Lbl(gateName,inds)] = embedded_op
                    primitive_ops.append(_Lbl(gateName,inds))

                except Exception as e:
                    if on_construction_error == 'warn':
                        _warnings.warn("Failed to embed %s gate %s. Dropping it." %
                                       (parameterization, str(_Lbl(gateName,inds))))
                    if on_construction_error in ('warn','ignore'): continue
                    else: raise e

        self.set_primitive_op_labels(primitive_ops)
        self.set_primitive_prep_labels(tuple(self.prep_blks.keys()))
        self.set_primitive_povm_labels(tuple(self.povm_blks.keys()))
        #(no instruments)

    
class SimpleCompLayerLizard(_mdl.ImplicitLayerLizard):
    def get_prep(self,layerlbl):
        return self.prep_blks[layerlbl] # prep_blks are full prep ops
    def get_effect(self,layerlbl):
        return self.effect_blks[layerlbl] # effect_blks are full effect ops
    def get_operation(self,layerlbl):
        dense = bool(self.model._sim_type == "matrix") # whether dense matrix gates should be created
        Composed = _op.ComposedDenseOp if dense else _op.ComposedOp
        components = layerlbl.components

        if len(components) == 1:
            return self.op_blks[components[0]]
        else:
            #Note: OK if len(components) == 0, as it's ok to have a composed gate with 0 factors
            return Composed([self.op_blks[l] for l in components], dim=self.model.dim,
                                evotype=self.model._evotype)