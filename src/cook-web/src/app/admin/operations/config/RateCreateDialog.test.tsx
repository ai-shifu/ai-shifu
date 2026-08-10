import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import RateCreateDialog from './RateCreateDialog';
import type { RateRow } from './rateConfig';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) =>
      values ? `${key}:${JSON.stringify(values)}` : key,
  }),
}));

jest.mock('@/components/ui/Dialog', () => ({
  Dialog: ({
    open,
    onOpenChange,
    children,
  }: React.PropsWithChildren<{
    open: boolean;
    onOpenChange: (open: boolean) => void;
  }>) =>
    open ? (
      <div data-testid='dialog'>
        <button
          type='button'
          aria-label='request dialog close'
          onClick={() => onOpenChange(false)}
        />
        {children}
      </div>
    ) : null,
  DialogContent: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DialogDescription: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DialogFooter: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DialogHeader: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  DialogTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>,
}));

jest.mock('@/components/ui/AlertDialog', () => ({
  AlertDialog: ({
    open,
    onOpenChange,
    children,
  }: React.PropsWithChildren<{
    open: boolean;
    onOpenChange: (open: boolean) => void;
  }>) =>
    open ? (
      <div data-testid='alert-dialog'>
        <button
          type='button'
          aria-label='request confirmation close'
          onClick={() => onOpenChange(false)}
        />
        {children}
      </div>
    ) : null,
  AlertDialogAction: ({
    children,
    ...props
  }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button
      type='button'
      {...props}
    >
      {children}
    </button>
  ),
  AlertDialogCancel: ({
    children,
    ...props
  }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button
      type='button'
      {...props}
    >
      {children}
    </button>
  ),
  AlertDialogContent: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  AlertDialogDescription: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  AlertDialogFooter: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  AlertDialogHeader: ({ children }: React.PropsWithChildren) => (
    <div>{children}</div>
  ),
  AlertDialogTitle: ({ children }: React.PropsWithChildren) => (
    <h3>{children}</h3>
  ),
}));

const baseline = {
  is_configured: true,
  unit_cost: 0.25,
  tts_chars_per_llm_token: 0.5,
};

const rateRow = (overrides: Partial<RateRow>): RateRow =>
  ({
    usage_type: 'llm',
    usage_type_code: 7401,
    provider: 'qwen',
    model: 'qwen/deepseek-v4-flash',
    rate_model: 'deepseek-v4-flash',
    display_name: 'DeepSeek V4 Flash',
    usage_scene: 'production',
    usage_scene_code: 7411,
    billing_metric: 'llm_output_tokens',
    billing_metric_code: 7453,
    unit_size: 1,
    credits_per_unit: 0,
    unit_cost: 0,
    multiplier: null,
    rounding_mode: 7461,
    status_code: 0,
    source: 'unconfigured',
    ...overrides,
  }) as RateRow;

describe('RateCreateDialog', () => {
  test('offers non-exact suggestions and creates a canonical LLM rate', async () => {
    const onCreate = jest.fn().mockResolvedValue(true);
    const onOpenChange = jest.fn();
    const { container } = render(
      <RateCreateDialog
        open
        usageType='llm'
        rows={[
          rateRow({ source: 'unconfigured' }),
          rateRow({
            source: 'exact',
            provider: 'ark',
            model: 'ark/exact-model',
            rate_model: 'exact-model',
          }),
        ]}
        baseline={baseline}
        pending={false}
        onOpenChange={onOpenChange}
        onCreate={onCreate}
      />,
    );

    expect(container.querySelector('option[value="qwen"]')).toBeInTheDocument();
    expect(
      container.querySelector('option[value="deepseek-v4-flash"]'),
    ).toBeInTheDocument();
    expect(
      container.querySelector('option[value="exact-model"]'),
    ).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('fields.provider'), {
      target: { value: 'qwen' },
    });
    fireEvent.change(screen.getByLabelText('fields.model'), {
      target: { value: 'deepseek-v4-flash' },
    });
    fireEvent.change(screen.getByLabelText('fields.multiplier'), {
      target: { value: '1.5' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'actions.continue' }));
    fireEvent.click(screen.getByRole('button', { name: 'actions.confirmAdd' }));

    await waitFor(() =>
      expect(onCreate).toHaveBeenCalledWith(
        {
          create_only: true,
          usage_type: 'llm',
          provider: 'qwen',
          model: 'qwen/deepseek-v4-flash',
          rate_model: 'deepseek-v4-flash',
          billing_metric: 'llm_output_tokens',
          unit_size: 1,
          credits_per_unit: 0.375,
          status: 'active',
        },
        {
          usageType: 'llm',
          provider: 'qwen',
          model: 'qwen/deepseek-v4-flash',
          rateModel: 'deepseek-v4-flash',
        },
      ),
    );
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  test('blocks a duplicate exact identity before confirmation', () => {
    const onCreate = jest.fn();
    render(
      <RateCreateDialog
        open
        usageType='llm'
        rows={[rateRow({ source: 'exact' })]}
        baseline={baseline}
        pending={false}
        onOpenChange={jest.fn()}
        onCreate={onCreate}
      />,
    );

    fireEvent.change(screen.getByLabelText('fields.provider'), {
      target: { value: 'qwen' },
    });
    fireEvent.change(screen.getByLabelText('fields.model'), {
      target: { value: 'deepseek-v4-flash' },
    });
    fireEvent.change(screen.getByLabelText('fields.multiplier'), {
      target: { value: '1' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'actions.continue' }));

    expect(screen.getByRole('alert')).toHaveTextContent(
      'create.errors.duplicate',
    );
    expect(screen.queryByTestId('alert-dialog')).not.toBeInTheDocument();
    expect(onCreate).not.toHaveBeenCalled();
  });

  test('keeps TTS form values after a failed request and submits a blank default tier', async () => {
    const onCreate = jest.fn().mockResolvedValue(false);
    render(
      <RateCreateDialog
        open
        usageType='tts'
        rows={[]}
        baseline={baseline}
        pending={false}
        onOpenChange={jest.fn()}
        onCreate={onCreate}
      />,
    );

    fireEvent.change(screen.getByLabelText('fields.provider'), {
      target: { value: 'tencent' },
    });
    fireEvent.change(screen.getByLabelText('fields.ttsMultiplier'), {
      target: { value: '2' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'actions.continue' }));
    fireEvent.click(screen.getByRole('button', { name: 'actions.confirmAdd' }));

    await waitFor(() =>
      expect(onCreate).toHaveBeenCalledWith(
        expect.objectContaining({
          usage_type: 'tts',
          provider: 'tencent',
          model: '',
          rate_model: '',
          billing_metric: 'tts_output_chars',
          credits_per_unit: 1,
        }),
        expect.any(Object),
      ),
    );
    await waitFor(() =>
      expect(screen.queryByTestId('alert-dialog')).not.toBeInTheDocument(),
    );
    expect(screen.getByLabelText('fields.provider')).toHaveValue('tencent');
    expect(screen.getByLabelText('fields.modelTier')).toHaveValue('');
    expect(screen.getByLabelText('fields.ttsMultiplier')).toHaveValue('2');
  });

  test('prevents dialog and confirmation closure while pending', () => {
    const onOpenChange = jest.fn();
    const props = {
      open: true,
      usageType: 'llm' as const,
      rows: [] as RateRow[],
      baseline,
      onOpenChange,
      onCreate: jest.fn().mockResolvedValue(true),
    };
    const { rerender } = render(
      <RateCreateDialog
        {...props}
        pending={false}
      />,
    );

    fireEvent.change(screen.getByLabelText('fields.provider'), {
      target: { value: 'qwen' },
    });
    fireEvent.change(screen.getByLabelText('fields.model'), {
      target: { value: 'new-model' },
    });
    fireEvent.change(screen.getByLabelText('fields.multiplier'), {
      target: { value: '1' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'actions.continue' }));
    expect(screen.getByTestId('alert-dialog')).toBeInTheDocument();

    rerender(
      <RateCreateDialog
        {...props}
        pending
      />,
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'request dialog close' }),
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'request confirmation close' }),
    );

    expect(onOpenChange).not.toHaveBeenCalled();
    expect(screen.getByTestId('dialog')).toBeInTheDocument();
    expect(screen.getByTestId('alert-dialog')).toBeInTheDocument();
  });

  test('uses single-flight protection for rapid confirmation clicks', async () => {
    let finishCreate: ((created: boolean) => void) | undefined;
    const onCreate = jest.fn(
      () =>
        new Promise<boolean>(resolve => {
          finishCreate = resolve;
        }),
    );
    render(
      <RateCreateDialog
        open
        usageType='llm'
        rows={[]}
        baseline={baseline}
        pending={false}
        onOpenChange={jest.fn()}
        onCreate={onCreate}
      />,
    );

    fireEvent.change(screen.getByLabelText('fields.provider'), {
      target: { value: 'qwen' },
    });
    fireEvent.change(screen.getByLabelText('fields.model'), {
      target: { value: 'new-model' },
    });
    fireEvent.change(screen.getByLabelText('fields.multiplier'), {
      target: { value: '1' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'actions.continue' }));
    const confirmButton = screen.getByRole('button', {
      name: 'actions.confirmAdd',
    });
    fireEvent.click(confirmButton);
    fireEvent.click(confirmButton);

    expect(onCreate).toHaveBeenCalledTimes(1);
    finishCreate?.(false);
    await waitFor(() =>
      expect(screen.queryByTestId('alert-dialog')).not.toBeInTheDocument(),
    );
  });
});
