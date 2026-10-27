import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';

import ImportActivationDialog from './ImportActivationDialog';

const mockGetAdminOrderShifus = jest.fn();
const mockImportActivationOrder = jest.fn();
const mockToast = jest.fn();
const mockTrackEvent = jest.fn();
const mockEnvState = {
  loginMethodsEnabled: ['phone'],
  defaultLoginMethod: 'phone',
};
const mockTranslate = jest.fn((key: string) => key);

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getAdminOrderShifus: (...args: unknown[]) =>
      mockGetAdminOrderShifus(...args),
    importActivationOrder: (...args: unknown[]) =>
      mockImportActivationOrder(...args),
  },
}));

jest.mock('@/store', () => ({
  useEnvStore: (selector: (state: typeof mockEnvState) => unknown) =>
    selector(mockEnvState),
}));

jest.mock('@/hooks/useTracking', () => ({
  useTracking: () => ({ trackEvent: mockTrackEvent }),
}));

jest.mock('@/hooks/useToast', () => ({
  useToast: () => ({ toast: mockToast }),
}));

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: mockTranslate,
    i18n: { language: 'en-US' },
  }),
}));

const renderBoundDialog = (
  props: Partial<React.ComponentProps<typeof ImportActivationDialog>> = {},
) => {
  const onOpenChange = jest.fn();
  const onSuccess = jest.fn();
  render(
    <ImportActivationDialog
      open
      onOpenChange={onOpenChange}
      onSuccess={onSuccess}
      initialCourseId='private-course'
      initialCourseName='Private course name'
      {...props}
    />,
  );
  return { onOpenChange, onSuccess };
};

const reviewList = async (value: string) => {
  const contact = screen.getByLabelText(
    'module.order.importActivation.mobileLabel',
  );
  fireEvent.change(contact, { target: { value } });
  fireEvent.submit(contact.closest('form')!);
  await screen.findByRole('alertdialog');
  expect(mockImportActivationOrder).not.toHaveBeenCalled();
  expect(mockTrackEvent).not.toHaveBeenCalled();
  return contact;
};

const confirmImport = () =>
  fireEvent.click(
    screen.getByRole('button', {
      name: 'module.order.importActivation.confirmSubmit',
    }),
  );

const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
};

describe('ImportActivationDialog validation', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockTrackEvent.mockReset();
    mockImportActivationOrder.mockReset();
    mockEnvState.loginMethodsEnabled = ['phone'];
    mockEnvState.defaultLoginMethod = 'phone';
    mockGetAdminOrderShifus.mockResolvedValue({ items: [] });
    mockImportActivationOrder.mockImplementation(
      async ({ lines }: { lines: string[] }) => ({
        success: lines.map(line => ({ mobile: line.split(/\s+/)[0] })),
        failed: [],
      }),
    );
  });

  it('shows both required field errors without opening import confirmation', async () => {
    render(
      <ImportActivationDialog
        open
        onOpenChange={jest.fn()}
      />,
    );

    const contact = screen.getByLabelText(
      'module.order.importActivation.mobileLabel',
    );
    fireEvent.submit(contact.closest('form')!);

    expect(
      await screen.findByText('module.order.importActivation.mobileRequired'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('module.order.importActivation.courseRequired'),
    ).toBeInTheDocument();
    expect(contact).toHaveAttribute('aria-invalid', 'true');
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(mockImportActivationOrder).not.toHaveBeenCalled();
  });

  it.each([
    {
      mode: 'phone',
      label: 'mobileLabel',
      required: 'mobileRequired',
      invalid: 'mobileInvalidLines',
      valid: '13800138000',
    },
    {
      mode: 'email',
      label: 'mobileLabel',
      required: 'mobileRequired',
      invalid: 'mobileInvalidLines',
      valid: 'learner@example.test',
    },
  ])(
    'validates empty and invalid $mode contacts before allowing confirmed import',
    async ({ mode, label, required, invalid, valid }) => {
      mockEnvState.loginMethodsEnabled = [mode];
      mockEnvState.defaultLoginMethod = mode;
      const onSuccess = jest.fn();
      const onOpenChange = jest.fn();
      render(
        <ImportActivationDialog
          open
          onOpenChange={onOpenChange}
          onSuccess={onSuccess}
          initialCourseId='course-1'
          initialCourseName='Course'
        />,
      );

      const contact = screen.getByLabelText(
        `module.order.importActivation.${label}`,
      );
      expect(
        screen.getByText('module.order.importActivation.mobileHint'),
      ).toBeInTheDocument();
      expect(
        screen.getByText('module.order.importActivation.nicknameHint'),
      ).toBeInTheDocument();
      const form = contact.closest('form')!;
      fireEvent.change(contact, { target: { value: '   ' } });
      fireEvent.submit(form);
      expect(
        await screen.findByText(`module.order.importActivation.${required}`),
      ).toBeInTheDocument();
      expect(mockImportActivationOrder).not.toHaveBeenCalled();

      fireEvent.change(contact, { target: { value: 'invalid contact' } });
      fireEvent.submit(form);
      expect(
        await screen.findByText(`module.order.importActivation.${invalid}`),
      ).toBeInTheDocument();
      expect(mockImportActivationOrder).not.toHaveBeenCalled();
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();

      fireEvent.change(contact, { target: { value: `  ${valid}  ` } });
      fireEvent.submit(form);
      expect(await screen.findByRole('alertdialog')).toBeInTheDocument();
      expect(mockTranslate).toHaveBeenCalledWith(
        'module.order.importActivation.confirmDescription',
        { mobiles: valid, count: 1, courseName: 'Course' },
      );
      expect(mockImportActivationOrder).not.toHaveBeenCalled();
      fireEvent.click(
        screen.getByRole('button', {
          name: 'module.order.importActivation.confirmSubmit',
        }),
      );

      await waitFor(() =>
        expect(mockImportActivationOrder).toHaveBeenCalledWith({
          lines: [valid],
          course_id: 'course-1',
          contact_type: mode,
        }),
      );
      expect(mockImportActivationOrder).toHaveBeenCalledTimes(1);
      await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
      expect(onSuccess).toHaveBeenCalledWith('');
    },
  );
  it('hides the bound course field without fetching selectable courses and keeps the review course', async () => {
    renderBoundDialog();
    expect(
      screen.queryByText('module.order.importActivation.courseLabel'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByDisplayValue('Private course name'),
    ).not.toBeInTheDocument();
    expect(mockGetAdminOrderShifus).not.toHaveBeenCalled();
    await reviewList('13800138000');
    expect(mockTranslate).toHaveBeenCalledWith(
      'module.order.importActivation.confirmDescription',
      {
        mobiles: '13800138000',
        count: 1,
        courseName: 'Private course name',
      },
    );
    confirmImport();
    await waitFor(() =>
      expect(mockImportActivationOrder).toHaveBeenCalledWith({
        lines: ['13800138000'],
        course_id: 'private-course',
        contact_type: 'phone',
      }),
    );
  });

  it('keeps the published-course selector and order-page analytics for an unbound entry', async () => {
    mockGetAdminOrderShifus.mockResolvedValue({
      items: [{ bid: 'selected-course', name: 'Selected course' }],
    });
    const onSuccess = jest.fn();
    render(
      <ImportActivationDialog
        open
        onOpenChange={jest.fn()}
        onSuccess={onSuccess}
      />,
    );
    await waitFor(() =>
      expect(mockGetAdminOrderShifus).toHaveBeenCalledWith({
        page_index: 1,
        page_size: 100,
        published: true,
      }),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.order.importActivation.courseLabel',
      }),
    );
    fireEvent.click(
      await screen.findByRole('button', { name: 'Selected course' }),
    );
    await reviewList('learner@example.test');
    expect(mockTranslate).toHaveBeenCalledWith(
      'module.order.importActivation.confirmDescription',
      {
        mobiles: 'learner@example.test',
        count: 1,
        courseName: 'Selected course',
      },
    );
    confirmImport();
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(mockImportActivationOrder).toHaveBeenCalledWith({
      lines: ['learner@example.test'],
      course_id: 'selected-course',
      contact_type: 'email',
    });
    expect(mockTrackEvent).toHaveBeenNthCalledWith(
      1,
      'creator_course_activation_attempt',
      { surface: 'admin_orders', contact_mode: 'email', requested_count: 1 },
    );
  });

  it('accepts a mixed list independently of the login mode and preserves each row nickname', async () => {
    mockEnvState.loginMethodsEnabled = ['phone'];
    const { onOpenChange } = renderBoundDialog();
    await reviewList(
      '  LEARNER@Example.test Ada  \n13800138000 Lin\n12345678901@example.test Bo',
    );
    confirmImport();
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(mockImportActivationOrder).toHaveBeenCalledTimes(2);
    expect(mockImportActivationOrder).toHaveBeenCalledWith({
      lines: ['13800138000 Lin'],
      course_id: 'private-course',
      contact_type: 'phone',
    });
    expect(mockImportActivationOrder).toHaveBeenCalledWith({
      lines: ['learner@example.test Ada', '12345678901@example.test Bo'],
      course_id: 'private-course',
      contact_type: 'email',
    });
    expect(mockTrackEvent.mock.calls).toEqual([
      [
        'creator_course_activation_attempt',
        {
          surface: 'admin_course_list',
          contact_mode: 'mixed',
          requested_count: 3,
        },
      ],
      [
        'creator_course_activation_result',
        {
          surface: 'admin_course_list',
          contact_mode: 'mixed',
          requested_count: 3,
          outcome: 'success',
          success_count: 3,
          failed_count: 0,
          failure_category: 'none',
        },
      ],
    ]);
    for (const [, payload] of mockTrackEvent.mock.calls) {
      for (const key of [
        'course_id',
        'mobile',
        'email',
        'nickname',
        'lines',
        'title',
        'error',
        'url',
      ])
        expect(payload).not.toHaveProperty(key);
    }
    const events = JSON.stringify(mockTrackEvent.mock.calls);
    for (const value of [
      'private-course',
      'Private course name',
      'learner@example.test',
      '13800138000',
      'Ada',
      'Lin',
    ])
      expect(events).not.toContain(value);
  });

  it('passes a default nickname through the existing field instead of parsing it as another account', async () => {
    const { onOpenChange } = renderBoundDialog();
    fireEvent.change(
      screen.getByLabelText('module.order.importActivation.nicknameLabel'),
      { target: { value: 'Default 13900139000 Name' } },
    );
    await reviewList('13800138000\nlearner@example.test Ada');
    confirmImport();
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(mockImportActivationOrder).toHaveBeenCalledWith({
      lines: ['13800138000'],
      user_nick_name: 'Default 13900139000 Name',
      course_id: 'private-course',
      contact_type: 'phone',
    });
    expect(mockImportActivationOrder).toHaveBeenCalledWith({
      lines: ['learner@example.test Ada'],
      user_nick_name: 'Default 13900139000 Name',
      course_id: 'private-course',
      contact_type: 'email',
    });
  });

  it('rejects email duplicates without regard to case before confirmation or tracking', async () => {
    renderBoundDialog();
    const contact = screen.getByLabelText(
      'module.order.importActivation.mobileLabel',
    );
    fireEvent.change(contact, {
      target: {
        value:
          'LEARNER@example.test Ada\nlearner@EXAMPLE.test Lin\n13800138000',
      },
    });
    fireEvent.submit(contact.closest('form')!);
    await screen.findByText('module.order.importActivation.mobileDuplicate');
    expect(mockTranslate).toHaveBeenCalledWith(
      'module.order.importActivation.mobileDuplicate',
      { numbers: 'learner@example.test' },
    );
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(mockImportActivationOrder).not.toHaveBeenCalled();
    expect(mockTrackEvent).not.toHaveBeenCalled();
  });

  it.each([
    '13800138000 learner@example.test',
    'learner@example.test> Ada',
    'invalid@example',
    '13800138000\ninvalid contact',
  ])(
    'rejects an invalid mixed-list row without losing its contents: %s',
    async value => {
      renderBoundDialog();
      const contact = screen.getByLabelText(
        'module.order.importActivation.mobileLabel',
      );
      fireEvent.change(contact, { target: { value } });
      fireEvent.blur(contact);
      expect(contact).toHaveValue(value);
      fireEvent.submit(contact.closest('form')!);
      await screen.findByText(
        'module.order.importActivation.mobileInvalidLines',
      );
      expect(mockImportActivationOrder).not.toHaveBeenCalled();
      expect(mockTrackEvent).not.toHaveBeenCalled();
    },
  );

  it.each([50, 51])(
    'enforces a total mixed-list limit before splitting %s rows',
    async count => {
      renderBoundDialog();
      const lines = Array.from({ length: count }, (_, index) =>
        index % 2
          ? `learner-${index}@example.test`
          : String(13800138000 + index),
      );
      const contact = screen.getByLabelText(
        'module.order.importActivation.mobileLabel',
      );
      fireEvent.change(contact, { target: { value: lines.join('\n') } });
      fireEvent.submit(contact.closest('form')!);
      if (count === 51) {
        await screen.findByText('module.order.importActivation.mobileLimit');
        expect(mockImportActivationOrder).not.toHaveBeenCalled();
        expect(mockTrackEvent).not.toHaveBeenCalled();
        return;
      }
      await screen.findByRole('alertdialog');
      confirmImport();
      await waitFor(() => expect(mockTrackEvent).toHaveBeenCalledTimes(2));
      expect(mockImportActivationOrder).toHaveBeenCalledTimes(2);
      expect(
        mockImportActivationOrder.mock.calls.map(
          ([payload]) => payload.lines.length,
        ),
      ).toEqual([25, 25]);
      expect(mockTrackEvent).toHaveBeenLastCalledWith(
        'creator_course_activation_result',
        {
          surface: 'admin_course_list',
          contact_mode: 'mixed',
          requested_count: 50,
          outcome: 'success',
          success_count: 50,
          failed_count: 0,
          failure_category: 'none',
        },
      );
    },
  );

  it.each(['phone', 'email'])(
    'keeps the other group successes when the %s request rejects and preserves every account reason',
    async rejectedType => {
      mockImportActivationOrder.mockImplementation(
        async ({
          contact_type,
          lines,
        }: {
          contact_type: string;
          lines: string[];
        }) => {
          if (contact_type === rejectedType)
            throw new Error('Request could not be confirmed');
          return { success: lines.map(line => ({ mobile: line })), failed: [] };
        },
      );
      const { onSuccess, onOpenChange } = renderBoundDialog();
      await reviewList(
        '13800138000\n13900139000\nfirst@example.test\nsecond@example.test',
      );
      confirmImport();
      await waitFor(() =>
        expect(screen.getByRole('status')).toHaveTextContent(
          'module.order.importActivation.partialSummary',
        ),
      );
      expect(mockTranslate).toHaveBeenCalledWith(
        'module.order.importActivation.partialSummary',
        { successCount: 2, failedCount: 2 },
      );
      expect(screen.getAllByRole('listitem')).toHaveLength(2);
      const failures =
        rejectedType === 'phone'
          ? ['13800138000', '13900139000']
          : ['first@example.test', 'second@example.test'];
      failures.forEach((account, index) => {
        expect(screen.getAllByRole('listitem')[index]).toHaveTextContent(
          account,
        );
        expect(screen.getAllByRole('listitem')[index]).toHaveTextContent(
          'Request could not be confirmed',
        );
      });
      expect(onSuccess).toHaveBeenCalledTimes(1);
      expect(onOpenChange).not.toHaveBeenCalled();
      expect(mockTrackEvent).toHaveBeenLastCalledWith(
        'creator_course_activation_result',
        {
          surface: 'admin_course_list',
          contact_mode: 'mixed',
          requested_count: 4,
          outcome: 'partial',
          success_count: 2,
          failed_count: 2,
          failure_category: 'request_failed',
        },
      );
      expect(JSON.stringify(mockTrackEvent.mock.calls)).not.toContain(
        'Request could not be confirmed',
      );
    },
  );

  it('combines backend partial results and displays all failure reasons beyond the toast sample', async () => {
    const phones = Array.from({ length: 6 }, (_, index) =>
      String(13800138000 + index),
    );
    mockImportActivationOrder.mockImplementation(
      async ({
        contact_type,
        lines,
      }: {
        contact_type: string;
        lines: string[];
      }) =>
        contact_type === 'phone'
          ? {
              success: [],
              failed: lines.map((mobile, index) => ({
                mobile,
                message: `Reason ${index}`,
              })),
            }
          : {
              success: [{ mobile: 'learner@example.test' }],
              failed: [
                { mobile: 'other@example.test', message: 'Already activated' },
              ],
            },
    );
    const { onSuccess, onOpenChange } = renderBoundDialog();
    await reviewList(
      [...phones, 'learner@example.test', 'other@example.test'].join('\n'),
    );
    confirmImport();
    await waitFor(() =>
      expect(screen.getAllByRole('listitem')).toHaveLength(7),
    );
    expect(screen.getAllByRole('listitem')[5]).toHaveTextContent(
      `${phones[5]}Reason 5`,
    );
    expect(screen.getAllByRole('listitem')[6]).toHaveTextContent(
      'other@example.testAlready activated',
    );
    expect(onSuccess).toHaveBeenCalledTimes(1);
    expect(onOpenChange).not.toHaveBeenCalled();
    expect(mockTrackEvent).toHaveBeenLastCalledWith(
      'creator_course_activation_result',
      {
        surface: 'admin_course_list',
        contact_mode: 'mixed',
        requested_count: 8,
        outcome: 'partial',
        success_count: 1,
        failed_count: 7,
        failure_category: 'item_failed',
      },
    );
  });

  it('treats accounts omitted from a response as unconfirmed rather than reporting total success', async () => {
    mockImportActivationOrder.mockImplementation(
      async ({ contact_type }: { contact_type: string }) =>
        contact_type === 'phone'
          ? { success: [{ mobile: '13800138000' }], failed: [] }
          : {},
    );
    const { onOpenChange } = renderBoundDialog();
    await reviewList('13800138000\nlearner@example.test');
    confirmImport();
    await waitFor(() =>
      expect(screen.getByRole('listitem')).toHaveTextContent(
        'learner@example.test',
      ),
    );
    expect(onOpenChange).not.toHaveBeenCalled();
    expect(mockTrackEvent).toHaveBeenLastCalledWith(
      'creator_course_activation_result',
      {
        surface: 'admin_course_list',
        contact_mode: 'mixed',
        requested_count: 2,
        outcome: 'partial',
        success_count: 1,
        failed_count: 1,
        failure_category: 'incomplete_response',
      },
    );
  });

  it('waits for both groups, records one terminal result and blocks re-entry while importing', async () => {
    const phone = deferred<{
      success: { mobile: string }[];
      failed: never[];
    }>();
    const email = deferred<{
      success: { mobile: string }[];
      failed: never[];
    }>();
    mockImportActivationOrder.mockImplementation(
      ({ contact_type }: { contact_type: string }) =>
        contact_type === 'phone' ? phone.promise : email.promise,
    );
    const { onOpenChange } = renderBoundDialog();
    const contact = await reviewList('13800138000\nlearner@example.test');
    const form = contact.closest('form')!;
    confirmImport();
    await waitFor(() =>
      expect(mockImportActivationOrder).toHaveBeenCalledTimes(2),
    );
    expect(mockTrackEvent).toHaveBeenCalledTimes(1);
    expect(contact).toBeDisabled();
    expect(
      screen.getByRole('button', { name: 'common.core.cancel' }),
    ).toBeDisabled();
    fireEvent.submit(form);
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    await act(async () =>
      phone.resolve({ success: [{ mobile: '13800138000' }], failed: [] }),
    );
    expect(mockTrackEvent).toHaveBeenCalledTimes(1);
    expect(onOpenChange).not.toHaveBeenCalled();
    await act(async () =>
      email.resolve({
        success: [{ mobile: 'learner@example.test' }],
        failed: [],
      }),
    );
    await waitFor(() => expect(mockTrackEvent).toHaveBeenCalledTimes(2));
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(mockImportActivationOrder).toHaveBeenCalledTimes(2);
  });

  it('reports a fully failed request once without claiming successful activation', async () => {
    mockImportActivationOrder.mockRejectedValue(
      new Error('Private API failure'),
    );
    const { onSuccess, onOpenChange } = renderBoundDialog();
    await reviewList('13800138000');
    confirmImport();
    await waitFor(() =>
      expect(screen.getByRole('listitem')).toHaveTextContent(
        '13800138000Private API failure',
      ),
    );
    expect(onSuccess).not.toHaveBeenCalled();
    expect(onOpenChange).not.toHaveBeenCalled();
    expect(mockTrackEvent.mock.calls).toEqual([
      [
        'creator_course_activation_attempt',
        {
          surface: 'admin_course_list',
          contact_mode: 'phone',
          requested_count: 1,
        },
      ],
      [
        'creator_course_activation_result',
        {
          surface: 'admin_course_list',
          contact_mode: 'phone',
          requested_count: 1,
          outcome: 'failed',
          success_count: 0,
          failed_count: 1,
          failure_category: 'request_failed',
        },
      ],
    ]);
  });

  it.each(['throw', 'reject', 'pending'])(
    'does not delay mixed import or completion when tracking is %s',
    async failure => {
      if (failure === 'throw')
        mockTrackEvent.mockImplementation(() => {
          throw new Error('Tracking unavailable');
        });
      if (failure === 'reject')
        mockTrackEvent.mockRejectedValue(new Error('Tracking unavailable'));
      if (failure === 'pending')
        mockTrackEvent.mockReturnValue(new Promise(() => {}));
      const { onSuccess, onOpenChange } = renderBoundDialog();
      await reviewList('13800138000\nlearner@example.test');
      confirmImport();
      await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
      expect(mockImportActivationOrder).toHaveBeenCalledTimes(2);
      expect(mockTrackEvent).toHaveBeenCalledTimes(2);
      expect(onSuccess).toHaveBeenCalledTimes(1);
    },
  );

  it('does not send an attempt when the review is cancelled', async () => {
    renderBoundDialog();
    await reviewList('13800138000\nlearner@example.test');
    fireEvent.click(
      screen.getByRole('button', {
        name: 'module.order.importActivation.backToEdit',
      }),
    );
    await waitFor(() =>
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument(),
    );
    expect(mockTrackEvent).not.toHaveBeenCalled();
    expect(mockImportActivationOrder).not.toHaveBeenCalled();
  });
});
