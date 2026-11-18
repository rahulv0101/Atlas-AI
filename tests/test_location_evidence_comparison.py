from copy import deepcopy
from atlas_ai.vision.evidence_alignment import build_evidence_alignment


def test_location_disagreement_does_not_modify_or_certify_visual_evidence():
    status={'timeframe':'M5','chart_features':{'location_state':'pullback','momentum_state':'strong'}}
    visual={'visual_features':{'visual_location':'mid_range','visual_momentum':'strong'}}
    before=deepcopy((status,visual))
    result=build_evidence_alignment(status,visual)
    comparison=result['location_comparison']
    assert comparison['relation']=='different'
    assert comparison['same_bar_mapping_verified'] is False
    assert result['screen_bar_matches_current'] is None
    assert (status,visual)==before


def test_matching_location_labels_do_not_certify_bar_mapping():
    result=build_evidence_alignment({'chart_features':{'location_state':'pullback'}},
        {'visual_features':{'visual_location':'pullback'}})
    assert result['location_comparison']['relation']=='agree'
    assert not result['location_comparison']['same_bar_mapping_verified']
