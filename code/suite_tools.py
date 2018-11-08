from collections import OrderedDict
from itertools import product
import math

import numpy as np
from ballot_comparison import ballot_comparison_pvalue
from fishers_combination import  maximize_fisher_combined_pvalue, create_modulus
from sprt import ballot_polling_sprt


################################################################################
############################# Check valid inputs ###############################
################################################################################

def check_valid_audit_parameters(risk_limit, lambda_step, o1_rate, o2_rate,
                                 u1_rate, u2_rate, stratum_sizes, n_ratio,
                                 num_winners):
    """
    Check that the audit parameters supplied are valid.
    """
    assert (n_ratio >= 0) and (n_ratio <= 1), "n_ratio must be between 0 and 1"
    assert (risk_limit >= 0) and (risk_limit <= 1), \
        "risk_limit must be between 0 and 1"
    assert (lambda_step > 0), "lambda_step must be a positive number"
    assert (o1_rate >= 0) and (o2_rate >= 0) and (u1_rate >= 0) and \
           (u2_rate >= 0) and (o1_rate <= 1) and (o2_rate <= 1) and \
           (u1_rate <= 1) and (u2_rate <= 1), \
           "Ballot comparison error rates must be between 0 and 1"
    assert len(stratum_sizes) == 2, "There must be two strata"
    assert isinstance(stratum_sizes[0], int) and \
           isinstance(stratum_sizes[1], int), \
           "Stratum sizes must be integer values"
    assert isinstance(num_winners, int) and num_winners > 0, \
           "Invalid number of winners"


def check_valid_vote_counts(candidates, stratum_sizes):
    """
    Check that the candidates dict containing vote totals
    makes sense
    """

    cvr_votes = poll_votes = 0
    for votes in candidates.values():
        cvr_votes += votes[0]
        poll_votes += votes[1]
    assert cvr_votes <= stratum_sizes[0]
    assert poll_votes <= stratum_sizes[1]

################################################################################
##################### Set up candidate data structures #########################
################################################################################

def find_winners_losers(candidates, num_winners):
    """
    Transform the input candidates dict into an Ordered Dict with canonical
    order of candidates, compute vote margins, and determine winners and losers.
    """
    for votes in candidates.values():
        votes.append(votes[0]+votes[1])
    candidates = OrderedDict(sorted(candidates.items(), \
                    key=(lambda t: t[1][2]), reverse=True))

    winners = list(candidates.keys())[0:num_winners]
    losers = list(candidates.keys())[num_winners:]

    # Calculate (w, l) pairwise margins indexed by pairs
    margins = {}
    for x in product(winners, losers):
        margins[x] = candidates[x[0]][2] - candidates[x[1]][2]
    margins = OrderedDict(sorted(margins.items(), \
                key=(lambda t: t[1]), reverse=True))

    return (candidates, margins, winners, losers)


def print_reported_votes(candidates, winners, losers, margins, stratum_sizes):
    """
    Utility function to print the contest information
    """
    # Sum the votes in each stratum
    cvr_votes = poll_votes = 0
    for votes in candidates.values():
        cvr_votes += votes[0]
        poll_votes += votes[1]

    # Find the smallest margin between winners and losers
    min_margin = np.amin(list(margins.values()))

    print('\nTotal reported votes:\n\t\t\tCVR\tno-CVR\ttotal')
    for k, v in candidates.items():
        print('\t', k, ':', v[0], '\t', v[1], '\t', v[2])
    print('\n\t total votes:\t', cvr_votes, \
          '\t', poll_votes, '\t', \
          cvr_votes + poll_votes)
    print('\n\t non-votes:\t',\
          stratum_sizes[0] - cvr_votes, '\t',\
          stratum_sizes[1] - poll_votes, '\t',\
          stratum_sizes[0] + stratum_sizes[1] - cvr_votes - poll_votes\
         )

    print('\nwinners:')
    for w in winners:
        print('\t', w)

    print('\nlosers:')
    for ell in losers:
        print('\t', ell)

    print('\n\nmargins:')
    for k, v in margins.items():
        dum = k[0] + ' beat ' + k[1] + ' by'
        print('\t', dum, v, 'votes')

    print('\nsmallest margin:', min_margin, \
          '\ndiluted margin:', min_margin/np.sum(stratum_sizes))


################################################################################
########################## Sample size estimation ##############################
################################################################################


def estimate_n(N_w1, N_w2, N_l1, N_l2, N1, N2,\
               o1_rate=0, o2_rate=0, u1_rate=0, u2_rate=0,\
               n_ratio=None,
               risk_limit=0.05,\
               gamma=1.03905,\
               stepsize=0.05):
    """
    Estimate the initial sample sizes for the audit.

    Parameters
    ----------
    N_w1 : int
        votes for the reported winner in the ballot comparison stratum
    N_w2 : int
        votes for the reported winner in the ballot polling stratum
    N_l1 : int
        votes for the reported loser in the ballot comparison stratum
    N_l2 : int
        votes for the reported loser in the ballot polling stratum
    N1 : int
        total number of votes in the ballot comparison stratum
    N2 : int
        total number of votes in the ballot polling stratum
    o1_rate : float
        expected percent of ballots with 1-vote overstatements in
        the CVR stratum
    o2_rate : float
        expected percent of ballots with 2-vote overstatements in
        the CVR stratum
    u1_rate : float
        expected percent of ballots with 1-vote understatements in
        the CVR stratum
    u2_rate : float
        expected percent of ballots with 2-vote understatements in
        the CVR stratum
    n_ratio : float
        ratio of sample allocated to each stratum.
        If None, allocate sample in proportion to ballots cast in each stratum
    risk_limit : float
        risk limit
    gamma : float
        gamma from Lindeman and Stark (2012)
    stepsize : float
        stepsize for the discrete bounds on Fisher's combining function
    Returns
    -------
    tuple : estimated initial sample sizes in the CVR stratum and no-CVR stratum
    """
    n_ratio = n_ratio if n_ratio else N1/(N1+N2)
    n = 5
    reported_margin = (N_w1+N_w2)-(N_l1+N_l2)
    expected_pvalue = 1

    def try_n(n):
        """
        Find expected combined P-value for a total sample size n.
        """
        n1 = math.ceil(n_ratio * n)
        n2 = n - n1

        # Set up the p-value function for the CVR stratum
        if n1 == 0:
            cvr_pvalue = lambda alloc: 1
        else:
            o1 = math.ceil(o1_rate*n1)
            o2 = math.ceil(o2_rate*n1)
            u1 = math.floor(u1_rate*n1)
            u2 = math.floor(u2_rate*n1)
            cvr_pvalue = lambda alloc: ballot_comparison_pvalue(n=n1, \
                            gamma=gamma, o1=o1, u1=u1, o2=o2, u2=u2, \
                            reported_margin=reported_margin, N=N1, \
                            null_lambda=alloc)

        # Set up the p-value function for the no-CVR stratum
        if n2 == 0:
            nocvr_pvalue = lambda alloc: 1
        else:
            sample = np.array([0]*int(n2*N_l2/N2)+[1]*int(n2*N_w2/N2)+ \
                        [np.nan]*int(n2*(N2-N_l2-N_w2)/N2))
            nocvr_pvalue = lambda alloc: ballot_polling_sprt(sample=sample, \
                            popsize=N2, \
                            alpha=risk_limit,\
                            Vw=N_w2, Vl=N_l2, \
                            null_margin=(N_w2-N_l2) - \
                             alloc*reported_margin)['pvalue']

        bounding_fun = create_modulus(n1=n1, n2=n2,
                                      n_w2=int(n2*N_w2/N2), \
                                      n_l2=int(n2*N_l2/N2), \
                                      N1=N1, V_wl=reported_margin, gamma=gamma)
        res = maximize_fisher_combined_pvalue(N_w1=N_w1, N_l1=N_l1, N1=N1, \
                                              N_w2=N_w2, N_l2=N_l2, N2=N2, \
                                              pvalue_funs=(cvr_pvalue, \
                                               nocvr_pvalue), \
                                              stepsize=stepsize, \
                                              modulus=bounding_fun, \
                                              alpha=risk_limit)
        expected_pvalue = res['max_pvalue']
        if (n % 100) == 0:
            print('...trying...', n, expected_pvalue)
        return expected_pvalue

    # step 1: linear search, doubling n each time
    while (expected_pvalue > risk_limit) or (expected_pvalue is np.nan):
        n = 2*n
        expected_pvalue = try_n(n)

    # step 2: bisection between n/2 and n
    low_n = n/2
    high_n = n
    mid_pvalue = 1
    while  (mid_pvalue > risk_limit) or (expected_pvalue is np.nan):
        mid_n = np.floor((low_n+high_n)/2)
        mid_pvalue = try_n(mid_n)
        if mid_pvalue <= risk_limit:
            high_n = mid_n
        else:
            low_n = mid_n

    n1 = math.ceil(n_ratio * mid_n)
    n2 = int(mid_n - n1)
    return (n1, n2)


def estimate_escalation_n(N_w1, N_w2, N_l1, N_l2, N1, N2, n1, n2, \
                          o1_obs, o2_obs, u1_obs, u2_obs, \
                          n2l_obs, n2w_obs, \
                          o1_rate=0, o2_rate=0, u1_rate=0, u2_rate=0, \
                          n_ratio=None, \
                          risk_limit=0.05,\
                          gamma=1.03905,\
                          stepsize=0.05):
    """
    Estimate the initial sample sizes for the audit.

    Parameters
    ----------
    N_w1 : int
        votes for the reported winner in the ballot comparison stratum
    N_w2 : int
        votes for the reported winner in the ballot polling stratum
    N_l1 : int
        votes for the reported loser in the ballot comparison stratum
    N_l2 : int
        votes for the reported loser in the ballot polling stratum
    N1 : int
        total number of votes in the ballot comparison stratum
    N2 : int
        total number of votes in the ballot polling stratum
    n1 : int
        size of sample already drawn in the ballot comparison stratum
    n2 : int
        size of sample already drawn in the ballot polling stratum
    o1_obs : int
        observed number of ballots with 1-vote overstatements in the CVR stratum
    o2_obs : int
        observed number of ballots with 2-vote overstatements in the CVR stratum
    u1_obs : int
        observed number of ballots with 1-vote understatements in the CVR
        stratum
    u2_obs : int
        observed number of ballots with 2-vote understatements in the CVR
        stratum
    n2l_obs : int
        observed number of votes for the reported loser in the no-CVR stratum
    n2w_obs : int
        observed number of votes for the reported winner in the no-CVR stratum
    o1_rate : float
        expected percent of ballots with 1-vote overstatements in the CVR
        stratum
    o2_rate : float
        expected percent of ballots with 2-vote overstatements in the CVR
        stratum
    u1_rate : float
        expected percent of ballots with 1-vote understatements in the CVR
        stratum
    u2_rate : float
        expected percent of ballots with 2-vote understatements in the CVR
        stratum
    n_ratio : float
        ratio of sample allocated to each stratum.
        If None, allocate sample in proportion to ballots cast in each stratum
    risk_limit : float
        risk limit
    gamma : float
        gamma from Lindeman and Stark (2012)
    stepsize : float
        stepsize for the discrete bounds on Fisher's combining function
    Returns
    -------
    tuple : estimated initial sample sizes in the CVR stratum and no-CVR stratum
    """
    n_ratio = n_ratio if n_ratio else N1/(N1+N2)
    n = n1+n2
    reported_margin = (N_w1+N_w2)-(N_l1+N_l2)
    expected_pvalue = 1

    n1_original = n1
    n2_original = n2
    observed_nocvr_sample = [0]*n2l_obs + [1]*n2w_obs + \
                            [np.nan]*(n2_original-n2l_obs-n2w_obs)

    def try_n(n):
        n1 = math.ceil(n_ratio * n)
        n2 = int(n - n1)
        
        if (n1 < n1_original) or (n2 < n2_original):
            return 1

        # Set up the p-value function for the CVR stratum
        if n1 == 0:
            cvr_pvalue = lambda alloc: 1
        else:
            o1 = math.ceil(o1_rate*(n1-n1_original)) + o1_obs
            o2 = math.ceil(o2_rate*(n1-n1_original)) + o2_obs
            u1 = math.floor(u1_rate*(n1-n1_original)) + u1_obs
            u2 = math.floor(u2_rate*(n1-n1_original)) + u2_obs
            cvr_pvalue = lambda alloc: ballot_comparison_pvalue(n=n1,\
                                gamma=1.03905, o1=o1, \
                                u1=u1, o2=o2, u2=u2, \
                                reported_margin=reported_margin, N=N1, \
                                null_lambda=alloc)

        # Set up the p-value function for the no-CVR stratum
        if n2 == 0:
            nocvr_pvalue = lambda alloc: 1
            n_w2 = 0
            n_l2 = 0
        else:
            expected_new_sample = [0]*int((n2-n2_original)*N_l2/N2)+ \
                                  [1]*int((n2-n2_original)*N_w2/N2)+ \
                                [np.nan]*int((n2-n2_original)*(N2-N_l2-N_w2)/N2)
            totsample = observed_nocvr_sample+expected_new_sample
            if len(totsample) < n2:
                totsample += [np.nan]*(n2 - len(totsample))
            totsample = np.array(totsample)
            n_w2 = np.sum(totsample == 1)
            n_l2 = np.sum(totsample == 0)

            nocvr_pvalue = lambda alloc: ballot_polling_sprt( \
                            sample=totsample,\
                            popsize=N2, \
                            alpha=risk_limit,\
                            Vw=N_w2, Vl=N_l2, \
                            null_margin=(N_w2-N_l2) - \
                             alloc*reported_margin)['pvalue']

        # Compute combined p-value
        bounding_fun = create_modulus(n1=n1, n2=n2,
                                      n_w2=n_w2, \
                                      n_l2=n_l2, \
                                      N1=N1, V_wl=reported_margin, gamma=gamma)
        res = maximize_fisher_combined_pvalue(N_w1=N_w1, N_l1=N_l1, N1=N1, \
                                              N_w2=N_w2, N_l2=N_l2, N2=N2, \
                                              pvalue_funs=(cvr_pvalue,\
                                                nocvr_pvalue), \
                                              stepsize=stepsize, \
                                              modulus=bounding_fun, \
                                              alpha=risk_limit)
        expected_pvalue = res['max_pvalue']
        if (n % 100) == 0:
            print('...trying...', n, expected_pvalue)
        return expected_pvalue

    # step 1: linear search, increasing n by a factor of 1.1 each time
    while (expected_pvalue > risk_limit) or (expected_pvalue is np.nan):
        n = np.ceil(1.1*n)
        expected_pvalue = try_n(n)

    # step 2: bisection between n/1.1 and n
    low_n = n/1.1
    high_n = n
    mid_pvalue = 1
    while  (mid_pvalue > risk_limit) or (expected_pvalue is np.nan):
        mid_n = np.floor((low_n+high_n)/2)
        mid_pvalue = try_n(mid_n)
        if mid_pvalue <= risk_limit:
            high_n = mid_n
        else:
            low_n = mid_n

    n1 = math.ceil(n_ratio * mid_n)
    n2 = int(mid_n - n1)
    return (n1, n2)


################################################################################
########################## Ballot manifest tools ###############################
################################################################################


def parse_manifest(manifest):
    """
    Parses a ballot manifest.
    Identifiers are not necessarily unique *across* batches.

    Input
    -----
    a ballot manifest in the syntax described above

    Returns
    -------
    an ordered dict containing batch ID (key) and ballot identifiers within
    the batch, either from sequential enumeration or from the given labels.
    """
    ballot_manifest_dict = OrderedDict()
    for i in manifest:
        # assert that the entry is a string with a comma in it
        # pull out batch label
        (batch, val) = i.split(",")
        batch = batch.strip()
        val = val.strip()
        if batch in ballot_manifest_dict.keys():
            raise ValueError('batch is listed more than once')
        else:
            ballot_manifest_dict[batch] = []

        # parse what comes after the batch label
        if '(' in val:     # list of identifiers
            # TO DO: use regex to remove )(
            val = val[1:-1] # strip out the parentheses
            ballot_manifest_dict[batch] += [int(num) for num in val.split()]
        elif ':' in val:   # range of identifiers
            limits = val.split(':')
            ballot_manifest_dict[batch] += list(range(int(limits[0]), \
                                             int(limits[1])+1))
        else:  # this should be an integer number of ballots
            try:
                ballot_manifest_dict[batch] += list(range(1, int(val)+1))
            except:
                print('malformed row in ballot manifest:\n\t', i)
    return ballot_manifest_dict


def unique_manifest(parsed_manifest):
    """
    Create a single ballot manifest with unique IDs for each ballot.
    Identifiers are unique across batches, so the ballots can be considered
    in a canonical order.
    """
    second_manifest = {}
    ballots_counted = 0
    for batch in parsed_manifest.keys():
        batch_size = len(parsed_manifest[batch])
        second_manifest[batch] = list(range(ballots_counted + 1, \
                                    ballots_counted + batch_size + 1))
        ballots_counted += batch_size
    return second_manifest


def find_ballot(ballot_num, unique_ballot_manifest, parsed_ballot_manifest):
    """
    Find ballot among all the batches

    Input
    -----
    ballot_num : int
        a ballot number that was sampled
    unique_ballot_manifest : dict
        ballot manifest with unique IDs across batches
    parsed_ballot_manifest : dict
        ballot manifest with original ballot IDs supplied in the manifest

    Returns
    -------
    tuple : (original_ballot_label, batch_label, which_ballot_in_batch)
    """
    for batch, ballots in unique_ballot_manifest.items():
        if ballot_num in ballots:
            position = ballots.index(ballot_num) + 1
            original_ballot_label = parsed_ballot_manifest[batch][position]
            return (original_ballot_label, batch, position)
    print("Ballot %i not found" % ballot_num)
    return None


################################################################################
############################## Do the audit! ###################################
################################################################################

def audit_contest(candidates, winners, losers, stratum_sizes,\
                  n1, n2, o1_obs, o2_obs, u1_obs, u2_obs, observed_poll, \
                  risk_limit, gamma, stepsize):
    """
    Use SUITE to calculate risk of each (winner, loser) pair
    given the observed samples in the CVR and no-CVR strata.

    Parameters
    ----------
    candidates : dict
        OrderedDict with candidate names as keys and 
        [CVR votes, no-CVR votes, total votes] as values
    winners : list
        names of winners
    losers : list
        names of losers
    stratum_sizes : list
        list with total number of votes in the CVR and no-CVR strata
    n1 : int
        size of sample already drawn in the ballot comparison stratum
    n2 : int
        size of sample already drawn in the ballot polling stratum
    o1_obs : int
        observed number of ballots with 1-vote overstatements in the CVR stratum
    o2_obs : int
        observed number of ballots with 2-vote overstatements in the CVR stratum
    u1_obs : int
        observed number of ballots with 1-vote understatements in the CVR
        stratum
    u2_obs : int
        observed number of ballots with 2-vote understatements in the CVR
        stratum
    observed_poll : dict
        Dict with candidate names as keys and number of votes in the no-CVR
        stratum sample as values
    risk_limit : float
        risk limit
    gamma : float
        gamma from Lindeman and Stark (2012)
    stepsize : float
        stepsize for the discrete bounds on Fisher's combining function
    Returns
    -------
    dict : attained risk for each (winner, loser) pair in the contest
    """
    audit_pvalues = {}

    for k in product(winners, losers):
        N_w1 = candidates[k[0]][0]
        N_w2 = candidates[k[0]][1]
        N_l1 = candidates[k[1]][0]
        N_l2 = candidates[k[1]][1]
        reported_margin = (N_w1+N_w2)-(N_l1+N_l2)
        cvr_pvalue = lambda alloc: ballot_comparison_pvalue(n=n1, \
                        gamma=gamma, \
                        o1=o1_obs, u1=u1_obs, o2=o2_obs, u2=u2_obs, \
                        reported_margin=reported_margin, \
                        N=stratum_sizes[0], \
                        null_lambda=alloc)

        n2w = observed_poll[k[0]]
        n2l = observed_poll[k[1]]
        sam = np.array([0]*n2l+[1]*n2w+[np.nan]*(n2-n2w-n2l))
        nocvr_pvalue = lambda alloc: ballot_polling_sprt(\
                                sample=sam, \
                                popsize=stratum_sizes[1], \
                                alpha=risk_limit, \
                                Vw=N_w2, Vl=N_l2, \
                                null_margin=(N_w2-N_l2) - \
                                  alloc*reported_margin)['pvalue']
        bounding_fun = create_modulus(n1=n1, n2=n2, \
                                      n_w2=n2w, \
                                      n_l2=n2l, \
                                      N1=stratum_sizes[0], \
                                      V_wl=reported_margin, gamma=gamma)
        res = maximize_fisher_combined_pvalue(N_w1=N_w1, N_l1=N_l1,\
                         N1=stratum_sizes[0], \
                         N_w2=N_w2, N_l2=N_l2, \
                         N2=stratum_sizes[1], \
                         pvalue_funs=(cvr_pvalue, nocvr_pvalue), \
                         stepsize=stepsize, \
                         modulus=bounding_fun, \
                         alpha=risk_limit)
        audit_pvalues[k] = res['max_pvalue']

    return audit_pvalues
