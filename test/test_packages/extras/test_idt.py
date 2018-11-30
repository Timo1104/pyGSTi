from __future__ import print_function
from ..testutils import BaseTestCase, compare_files, temp_files
import unittest
import numpy as np
import pickle
import time

import pygsti
from pygsti.extras import idletomography as idt

#Helper functions
#Global dicts describing how to prep and measure in various bases
prepDict = { 'X': ('Gy',), 'Y': ('Gx',)*3, 'Z': (),
             '-X': ('Gy',)*3, '-Y': ('Gx',), '-Z': ('Gx','Gx')}
measDict = { 'X': ('Gy',)*3, 'Y': ('Gx',), 'Z': (),
             '-X': ('Gy',), '-Y': ('Gx',)*3, '-Z': ('Gx','Gx')}

#Global switches for debugging
hamiltonian=True
stochastic=True
affine=True


def get_fileroot(nQubits, maxMaxLen, errMag, spamMag, nSamples, simtype, idleErrorInFiducials):
    return temp_files + "/idletomog_%dQ_maxLen%d_errMag%.5f_spamMag%.5f_%s_%s_%s" % \
            (nQubits,maxMaxLen,errMag,spamMag,
             "nosampleerr" if (nSamples == "inf") else ("%dsamples" % nSamples),
             simtype, 'idleErrInFids' if idleErrorInFiducials else 'noIdleErrInFids')

def make_idle_tomography_data(nQubits, maxLengths=(0,1,2,4), errMags=(0.01,0.001), spamMag=0,
                              nSamplesList=(100,'inf'), simtype="map"):
    
    prepNoise = (456,spamMag) if spamMag > 0 else None
    povmNoise = (789,spamMag) if spamMag > 0 else None
    base_param = []
    if hamiltonian: base_param.append('H')
    if stochastic: base_param.append('S')
    if affine: base_param.append('A')
    base_param = '+'.join(base_param)
    parameterization = base_param+" terms" if simtype.startswith('termorder') else base_param # "H+S+A"
    
    gateset_idleInFids = pygsti.construction.build_nqnoise_gateset(nQubits, "line", [], min(2,nQubits), 1,
                                      sim_type=simtype, parameterization=parameterization,
                                      gateNoise=None, prepNoise=prepNoise, povmNoise=povmNoise,
                                      addIdleNoiseToAllGates=True)
    gateset_noIdleInFids = pygsti.construction.build_nqnoise_gateset(nQubits, "line", [], min(2,nQubits), 1,
                                      sim_type=simtype, parameterization=parameterization,
                                      gateNoise=None, prepNoise=prepNoise, povmNoise=povmNoise,
                                      addIdleNoiseToAllGates=False)
    
    listOfExperiments = idt.make_idle_tomography_list(nQubits, maxLengths, (prepDict,measDict), maxweight=min(2,nQubits),
                    include_hamiltonian=hamiltonian, include_stochastic=stochastic, include_affine=affine)
    
    base_vec = None
    for errMag in errMags:
        
        #ky = 'A(Z%s)' % ('I'*(nQubits-1)); debug_errdict = {ky: 0.01 }
        #ky = 'A(ZZ%s)' % ('I'*(nQubits-2)); debug_errdict = {ky: 0.01 }
        debug_errdict = {}
        if base_vec is None:
            rand_vec = idt.set_Gi_errors(nQubits, gateset_idleInFids, debug_errdict, rand_default=errMag,
                                        hamiltonian=hamiltonian, stochastic=stochastic, affine=affine)
            base_vec = rand_vec / errMag
            
        err_vec = base_vec * errMag # for different errMags just scale the *same* random rates
        idt.set_Gi_errors(nQubits, gateset_idleInFids, debug_errdict, rand_default=err_vec,
                          hamiltonian=hamiltonian, stochastic=stochastic, affine=affine)
        idt.set_Gi_errors(nQubits, gateset_noIdleInFids, debug_errdict, rand_default=err_vec,
                          hamiltonian=hamiltonian, stochastic=stochastic, affine=affine) # same errors for w/ and w/out idle fiducial error
    
        for nSamples in nSamplesList:
            if nSamples == 'inf':
                sampleError = 'none'; Nsamp = 100
            else:
                sampleError = 'multinomial'; Nsamp = nSamples
                                
            ds_idleInFids = pygsti.construction.generate_fake_data(
                                gateset_idleInFids, listOfExperiments, nSamples=Nsamp,
                                sampleError=sampleError, seed=8675309)
            fileroot = get_fileroot(nQubits, maxLengths[-1], errMag, spamMag, nSamples, simtype, True)
            pickle.dump(gateset_idleInFids, open("%s_gs.pkl" % fileroot, "wb"))
            pickle.dump(ds_idleInFids, open("%s_ds.pkl" % fileroot, "wb"))
            print("Wrote fileroot ",fileroot)
            
            ds_noIdleInFids = pygsti.construction.generate_fake_data(
                                gateset_noIdleInFids, listOfExperiments, nSamples=Nsamp,
                                sampleError=sampleError, seed=8675309)
                
            fileroot = get_fileroot(nQubits, maxLengths[-1], errMag, spamMag, nSamples, simtype, False) 
            pickle.dump(gateset_noIdleInFids, open("%s_gs.pkl" % fileroot, "wb"))
            pickle.dump(ds_noIdleInFids, open("%s_ds.pkl" % fileroot, "wb"))

            #FROM DEBUGGING Python2 vs Python3 issue (ended up being an ordered-dict)
            ##pygsti.io.write_dataset("%s_ds_chk.txt" % fileroot, ds_noIdleInFids)
            #chk = pygsti.io.load_dataset("%s_ds_chk.txt" % fileroot)
            #for gstr,dsrow in ds_noIdleInFids.items():
            #    for outcome in dsrow.counts:
            #        cnt1, cnt2 = dsrow.counts.get(outcome,0.0),chk[gstr].counts.get(outcome,0.0)
            #        if not np.isclose(cnt1,cnt2):
            #            raise ValueError("NOT EQUAL: %s != %s" % (str(dsrow.counts), str(chk[gstr].counts)))
            #print("EQUAL!")

            print("Wrote fileroot ",fileroot)
            
def helper_idle_tomography(nQubits, maxLengths=(1,2,4), file_maxLen=4, errMag=0.01, spamMag=0, nSamples=100,
                         simtype="map", idleErrorInFiducials=True, fitOrder=1, fileroot=None):   
    if fileroot is None:
        fileroot = get_fileroot(nQubits, file_maxLen, errMag, spamMag, nSamples, simtype, idleErrorInFiducials) 
            
    gs_datagen = pickle.load(open("%s_gs.pkl" % fileroot, "rb"))
    ds = pickle.load(open("%s_ds.pkl" % fileroot, "rb"))
    
    #print("DB: ",ds[ ('Gi',) ])
    #print("DB: ",ds[ ('Gi','Gi') ])
    #print("DB: ",ds[ ((('Gx',0),('Gx',1)),(('Gx',0),('Gx',1)),'Gi',(('Gx',0),('Gx',1)),(('Gx',0),('Gx',1))) ])
    
    advanced = {'fit order': fitOrder}
    results = idt.do_idle_tomography(nQubits, ds, maxLengths, (prepDict,measDict), maxweight=min(2,nQubits),
                                     advancedOptions=advanced, include_hamiltonian=hamiltonian,
                                     include_stochastic=stochastic, include_affine=affine)
        
    if hamiltonian: ham_intrinsic_rates = results.intrinsic_rates['hamiltonian']
    if stochastic:  sto_intrinsic_rates = results.intrinsic_rates['stochastic'] 
    if affine:      aff_intrinsic_rates = results.intrinsic_rates['affine'] 
        
    maxErrWeight=2 # hardcoded for now
    datagen_ham_rates, datagen_sto_rates, datagen_aff_rates = \
        idt.predicted_intrinsic_rates(nQubits, maxErrWeight, gs_datagen, hamiltonian, stochastic, affine)
    print("Predicted HAM = ",datagen_ham_rates)
    print("Predicted STO = ",datagen_sto_rates)
    print("Predicted AFF = ",datagen_aff_rates)
    print("Intrinsic HAM = ",ham_intrinsic_rates)
    print("Intrinsic STO = ",sto_intrinsic_rates)
    print("Intrinsic AFF = ",aff_intrinsic_rates)
    
    ham_diff = sto_diff = aff_diff = [0] # so max()=0 below for types we exclude
    if hamiltonian: ham_diff = np.abs(ham_intrinsic_rates - datagen_ham_rates)
    if stochastic:  sto_diff = np.abs(sto_intrinsic_rates - datagen_sto_rates)
    if affine:      aff_diff = np.abs(aff_intrinsic_rates - datagen_aff_rates)
    
    print("Err labels:", [ x.rep for x in results.error_list])
    if hamiltonian: print("Ham diffs:", ham_diff)
    if stochastic:  print("Sto diffs:", sto_diff)
    #if stochastic:
    #    for x,y in zip(sto_intrinsic_rates,datagen_sto_rates):
    #        print("  %g <--> %g" % (x,y))
    if affine:      print("Aff diffs:", aff_diff)
    print("%s\n MAX DIFFS: " % fileroot, max(ham_diff),max(sto_diff),max(aff_diff))
    return max(ham_diff),max(sto_diff),max(aff_diff)

#OLD - leftover from when we put data into a pandas data frame    
#     #add hamiltonian data to df
#     N = len(labels) # number of hamiltonian/stochastic rates
#     data = pd.DataFrame({'nQubits': [nQubits]*N, 'maxL':[maxLengths[-1]]*N,
#             'errMag': [errMag]*N, 'spamMag': [spamMag]*N,
#             'nSamples': [nSamples]*N,
#             'simtype': [simtype]*N, 'type': ['hamiltonian']*N,
#             'true_val': datagen_ham_rates, 'estimate': ham_intrinsic_rates,
#             'diff': ham_intrinsic_rates - datagen_ham_rates, 'abs_diff': ham_diff,
#             'fitOrder': [fitOrder]*N, 'idleErrorInFiducials': [idleErrorInFiducials]*N })
#     df = df.append(data, ignore_index=True)
    
#     #add stochastic data to df
#     data = pd.DataFrame({'nQubits': [nQubits]*N, 'maxL':[maxLengths[-1]]*N,
#             'errMag': [errMag]*N, 'spamMag': [spamMag]*N,
#             'nSamples': [nSamples]*N,
#             'simtype': [simtype]*N, 'type': ['stochastic']*N,
#             'true_val': datagen_sto_rates, 'estimate': sto_intrinsic_rates,
#             'diff': sto_intrinsic_rates - datagen_sto_rates,'abs_diff': sto_diff,
#             'fitOrder': [fitOrder]*N, 'idleErrorInFiducials': [idleErrorInFiducials]*N })
#     df = df.append(data, ignore_index=True)
#     return df


class IDTTestCase(BaseTestCase):

    def test_idletomography_1Q(self):        
        nQ = 1
        
        #make perfect data - using termorder:1 here means the data is not CPTP and
        # therefore won't be in [0,1], and creating a data set with sampleError="none"
        # means that probabilities *won't* be clipped to [0,1] - so we get really 
        # funky and unphysical data here, but data that idle tomography should be 
        # able to fit *exactly* (with any errMags, so be pick a big one).
        make_idle_tomography_data(nQ, maxLengths=(0,1,2,4), errMags=(0.01,), spamMag=0,
                                  nSamplesList=('inf',), simtype="termorder:1")

        # Note: no spam error, as accounting for this isn't build into idle tomography yet.
        maxH, maxS, maxA = helper_idle_tomography(nQ, maxLengths=(1,2,4), file_maxLen=4,
                                                errMag=0.01, spamMag=0, nSamples='inf',
                                                idleErrorInFiducials=False, fitOrder=1, simtype="termorder:1")

        #Make sure exact identification of errors was possible
        self.assertLess(maxH, 1e-6)
        self.assertLess(maxS, 1e-6)
        self.assertLess(maxA, 1e-6)

    def test_idletomography_2Q(self):        
        #Same thing but for 2 qubits
        nQ = 2
        make_idle_tomography_data(nQ, maxLengths=(0,1,2,4), errMags=(0.01,), spamMag=0,
                                  nSamplesList=('inf',), simtype="termorder:1")
        maxH, maxS, maxA = helper_idle_tomography(nQ, maxLengths=(1,2,4), file_maxLen=4,
                                                errMag=0.01, spamMag=0, nSamples='inf',
                                                idleErrorInFiducials=False, fitOrder=1, simtype="termorder:1")
        self.assertLess(maxH, 1e-6)
        self.assertLess(maxS, 1e-6)
        self.assertLess(maxA, 1e-6)

    def test_idletomog_gstdata_std1Q(self):
        from pygsti.construction import std1Q_XYI as std
        std = pygsti.construction.stdmodule_to_smqmodule(std)

        maxLens = [1,2,4]
        expList = pygsti.construction.make_lsgst_experiment_list(std.gs_target, std.prepStrs,
                                                                 std.effectStrs, std.germs_lite, maxLens)
        ds = pygsti.construction.generate_fake_data(std.gs_target.depolarize(0.01, 0.01),
                                                    expList, 1000, 'multinomial', seed=1234)

        result = pygsti.do_long_sequence_gst(ds, std.gs_target, std.prepStrs, std.effectStrs, std.germs_lite, maxLens, verbosity=3)

        #standard report will run idle tomography
        pygsti.report.create_standard_report(result, temp_files + "/gstWithIdleTomogTestReportStd1Q",
                                             "Test GST Report w/Idle Tomography Tab: StdXYI",
                                             verbosity=3, auto_open=False)

    def test_idletomog_gstdata_1Qofstd2Q(self):
        # perform idle tomography on first qubit of 2Q
        from pygsti.construction import std2Q_XYICNOT as std2Q
        from pygsti.construction import std1Q_XYI as std
        std2Q = pygsti.construction.stdmodule_to_smqmodule(std2Q)
        std = pygsti.construction.stdmodule_to_smqmodule(std)

        maxLens = [1,2,4]
        expList = pygsti.construction.make_lsgst_experiment_list(std2Q.gs_target, std2Q.prepStrs,
                                                                 std2Q.effectStrs, std2Q.germs_lite, maxLens)
        gs_datagen = std2Q.gs_target.depolarize(0.01, 0.01)
        ds2Q = pygsti.construction.generate_fake_data(gs_datagen, expList, 1000, 'multinomial', seed=1234)

        #Just analyze first qubit (qubit 0)
        ds = pygsti.construction.filter_dataset(ds2Q, (0,))

        start = std.gs_target.copy()
        start.set_all_parameterizations("TP")
        result = pygsti.do_long_sequence_gst(ds, start, std.prepStrs[0:4], std.effectStrs[0:4],
                                             std.germs_lite, maxLens, verbosity=3, advancedOptions={'objective': 'chi2'})
        #result = pygsti.do_model_test(start.depolarize(0.009,0.009), ds, std.gs_target.copy(), std.prepStrs[0:4],
        #                              std.effectStrs[0:4], std.germs_lite, maxLens)
        pygsti.report.create_standard_report(result, temp_files + "/gstWithIdleTomogTestReportStd1Qfrom2Q",
                                             "Test GST Report w/Idle Tomog.: StdXYI from StdXYICNOT",
                                             verbosity=3, auto_open=False)

    def test_idletomog_gstdata_nQ(self):
        #Global dicts describing how to prep and measure in various bases
        prepDict = { 'X': ('Gy',), 'Y': ('Gx',)*3, 'Z': (),
                     '-X': ('Gy',)*3, '-Y': ('Gx',), '-Z': ('Gx','Gx')}
        measDict = { 'X': ('Gy',)*3, 'Y': ('Gx',), 'Z': (),
                     '-X': ('Gy',), '-Y': ('Gx',)*3, '-Z': ('Gx','Gx')}

        nQubits = 2
        maxLengths = [1,2,4]
        
        ## ----- Generate n-qubit gate sequences -----
        c = {} #Uncomment to re-generate cache SAVE
        #c = pickle.load(open(compare_files+"/idt_nQsequenceCache%s.pkl" % self.versionsuffix,'rb'))
        
        t = time.time()
        gss = pygsti.construction.create_nqubit_sequences(nQubits, maxLengths, 'line', [(0,1)], maxIdleWeight=2,
                                                          idleOnly=False, paramroot="H+S", cache=c, verbosity=3)
        gss_strs = gss.allstrs
        print("%.1fs" % (time.time()-t))
        pickle.dump(c, open(compare_files+"/idt_nQsequenceCache%s.pkl" % self.versionsuffix,'wb')) #Uncomment to re-generate cache

        # To run idle tomography, we need "pauli fiducial pairs", so
        #  get fiducial pairs for Gi germ from gss and convert 
        #  to "Pauli fidicual pairs" (which pauli state/basis is prepared or measured)
        GiStr = pygsti.obj.GateString(('Gi',))
        self.assertTrue(GiStr in gss.germs)
        self.assertTrue(gss.Ls == maxLengths)
        L0 = maxLengths[0] # all lengths should have same fidpairs, just take first one
        plaq = gss.get_plaquette(L0, GiStr)
        pauli_fidpairs = idt.fidpairs_to_pauli_fidpairs(plaq.fidpairs, (prepDict,measDict), nQubits)

        print(plaq.fidpairs)
        print()
        print('\n'.join([ "%s, %s" % (p[0],p[1]) for p in pauli_fidpairs]))
        self.assertEqual(len(plaq.fidpairs), len(pauli_fidpairs))
        self.assertEqual(len(plaq.fidpairs), 16) # (will need to change this if use H+S+A above)

        # ---- Create some fake data ----
        gs_target = pygsti.construction.build_nqnoise_gateset(nQubits, "line", [(0,1)], 2, 1,
                                                              sim_type="map", parameterization="H+S")

        #Note: generate data with affine errors too (H+S+A used below)
        gs_datagen = pygsti.construction.build_nqnoise_gateset(nQubits, "line", [(0,1)], 2, 1,
                                                               sim_type="map", parameterization="H+S+A",
                                                               gateNoise=(1234,0.001), prepNoise=(1234,0.001), povmNoise=(1234,0.001))
        #This *only* (re)sets Gi errors...
        idt.set_Gi_errors(nQubits, gs_datagen, {}, rand_default=0.001,
                  hamiltonian=True, stochastic=True, affine=True) # no seed? FUTURE?
        ds = pygsti.construction.generate_fake_data(gs_datagen, gss.allstrs, 1000, 'multinomial', seed=1234)

        # ----- Run idle tomography with our custom (GST) set of pauli fiducial pairs ----
        advanced = {'pauli_fidpairs': pauli_fidpairs, 'jacobian mode': "together"}
        idtresults = idt.do_idle_tomography(nQubits, ds, maxLengths, (prepDict,measDict), maxweight=2,
                                     advancedOptions=advanced, include_hamiltonian='auto',
                                     include_stochastic='auto', include_affine='auto')
        #Note: inclue_affine="auto" should have detected that we don't have the sequences to 
        # determine the affine intrinsic rates:
        self.assertEqual(set(idtresults.intrinsic_rates.keys()), set(['hamiltonian','stochastic']))

        idt.create_idletomography_report(idtresults, temp_files + "/idleTomographyGSTSeqTestReport",
                                 "Test idle tomography report w/GST seqs", auto_open=False)

        
        #Run GST on the data (set tolerance high so this 2Q-GST run doesn't take long)
        gstresults = pygsti.do_long_sequence_gst_base(ds, gs_target, gss,
                                                      advancedOptions={'tolerance': 1e-1}, verbosity=3)

        #In FUTURE, we shouldn't need to set need to set the basis of our nQ GST results in order to make a report
        for estkey in gstresults.estimates: # 'default'
            gstresults.estimates[estkey].gatesets['go0'].basis = pygsti.obj.Basis("pp",4)
            gstresults.estimates[estkey].gatesets['target'].basis = pygsti.obj.Basis("pp",4)
        #pygsti.report.create_standard_report(gstresults, temp_files + "/gstWithIdleTomogTestReport", 
        #                                    "Test GST Report w/Idle Tomography Tab",
        #                                    verbosity=3, auto_open=False)
        pygsti.report.create_nqnoise_report(gstresults, temp_files + "/gstWithIdleTomogTestReport",
                                            "Test nQNoise Report w/Idle Tomography Tab",
                                            verbosity=3, auto_open=False)
        

    def test_automatic_paulidicts(self):
        expected_prepDict = { 'X': ('Gy',), 'Y': ('Gx',)*3, 'Z': (),
                              '-X': ('Gy',)*3, '-Y': ('Gx',), '-Z': ('Gx','Gx')}
        expected_measDict = { 'X': ('Gy',)*3, 'Y': ('Gx',), 'Z': (),
                              '-X': ('Gy',), '-Y': ('Gx',)*3, '-Z': ('Gx','Gx')}

        gs_target = pygsti.construction.build_nqnoise_gateset(3, "line", [(0,1)], 2, 1,
                                                      sim_type="map", parameterization="H+S+A")
        prepDict, measDict = idt.determine_paulidicts(gs_target)
        self.assertEqual(prepDict, expected_prepDict)
        self.assertEqual(measDict, expected_measDict)
        

if __name__ == '__main__':
    unittest.main(verbosity=2)


