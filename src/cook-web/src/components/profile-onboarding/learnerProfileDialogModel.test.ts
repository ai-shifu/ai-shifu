import {
  initialLearnerProfileDialogState,
  learnerProfileDialogReducer,
  selectLearnerProfileDialog,
} from './learnerProfileDialogModel';

describe('learnerProfileDialogModel', () => {
  it('derives dirty and save eligibility from one form snapshot', () => {
    const ready = learnerProfileDialogReducer(
      initialLearnerProfileDialogState,
      {
        type: 'patch',
        patch: { loadStatus: 'ready', phase: 'save' },
      },
    );
    const edited = learnerProfileDialogReducer(ready, {
      type: 'patch_form',
      patch: {
        profile: 'Learns visually',
        initialProfile: '',
        savedProfile: '',
      },
    });

    expect(
      selectLearnerProfileDialog(edited, 'dismissible', false),
    ).toMatchObject({
      loaded: true,
      dirty: true,
      canSave: true,
      normalizedProfile: 'Learns visually',
    });
  });

  it('derives busy states from the discriminated submission status', () => {
    const saving = learnerProfileDialogReducer(
      initialLearnerProfileDialogState,
      {
        type: 'patch',
        patch: { loadStatus: 'ready', submissionStatus: 'saving' },
      },
    );

    expect(
      selectLearnerProfileDialog(saving, 'dismissible', false),
    ).toMatchObject({
      saving: true,
      dismissing: false,
      deferring: false,
      busy: true,
      canSave: false,
    });
  });

  it('resets account-scoped form and request state together', () => {
    const previousAccount = learnerProfileDialogReducer(
      initialLearnerProfileDialogState,
      {
        type: 'patch_form',
        patch: { profile: 'Previous account' },
      },
    );
    const collecting = learnerProfileDialogReducer(previousAccount, {
      type: 'patch',
      patch: {
        phase: 'collect',
        collectionStatus: 'running',
        collectionRunInFlight: true,
        activeCollectionSessionId: 'session-previous',
        confirmation: 'discard',
      },
    });

    expect(
      learnerProfileDialogReducer(collecting, {
        type: 'reset',
        state: { loadStatus: 'loading' },
      }),
    ).toEqual({
      ...initialLearnerProfileDialogState,
      loadStatus: 'loading',
    });
  });
});
