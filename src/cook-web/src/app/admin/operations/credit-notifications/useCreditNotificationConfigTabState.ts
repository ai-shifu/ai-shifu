import { useMemo, useState, type Dispatch, type SetStateAction } from 'react';
import type { TFunction } from 'i18next';
import { toast } from '@/hooks/useToast';
import type {
  AdminOperationCreditNotificationPolicy,
  AdminOperationCreditNotificationPolicyListItem,
  AdminOperationCreditNotificationPolicyResolvedLists,
} from '../operation-credit-notification-types';
import {
  formatListInput,
  normalizeIntegerInput,
  normalizeListInputCharacters,
  parseListInput,
  readNumber,
  type KnownNotificationType,
} from './creditNotificationUtils';
import type { CreditNotificationManagedListType as ManagedListType } from './CreditNotificationManagedListDialog';

export type UpdatePolicy = (
  updater: (draft: AdminOperationCreditNotificationPolicy) => void,
) => void;

const MAX_BLOCKED_CREATOR_IMPORT_COUNT = 50;
const INVALID_SAMPLE_LIMIT = 5;
const PHONE_MATCH_PATTERN = /(?:^|\D)(\d{11})(?!\d)/g;
const EMAIL_MATCH_PATTERN = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;
const EMAIL_TEST_PATTERN = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/;
const CREATOR_ID_PATTERN = /^[A-Za-z0-9_-]{4,80}$/;

const isSmsMobileIdentifier = (value: string) => {
  const normalized = value.trim().replace(/^\+/, '');
  return /^\d{5,20}$/.test(normalized);
};

const findPhoneIdentifiers = (value: string): string[] => {
  const matches: string[] = [];
  const pattern = new RegExp(PHONE_MATCH_PATTERN.source, 'g');
  let match = pattern.exec(value);
  while (match) {
    if (match[1]) {
      matches.push(match[1]);
    }
    match = pattern.exec(value);
  }
  return matches;
};

const findEmailIdentifiers = (value: string): string[] =>
  Array.from(value.matchAll(EMAIL_MATCH_PATTERN)).map(match =>
    match[0].toLowerCase(),
  );

const splitIdentifierTokens = (value: string): string[] =>
  value
    .split(/[\s,;|]+/)
    .map(item => item.trim())
    .filter(Boolean);

const trimInvalidDisplay = (value: string): string =>
  value.replace(/^[\s,;|]+|[\s,;|]+$/g, '').trim();

const parseBlockedCreatorInput = (
  value: string,
  contactMode: 'email' | 'phone',
) => {
  const normalized = normalizeListInputCharacters(value).replace(/\t/g, ' ');
  const creatorBids: string[] = [];
  const mobiles: string[] = [];
  const invalidItems: string[] = [];
  const addToken = (token: string) => {
    if (isSmsMobileIdentifier(token)) {
      mobiles.push(token);
      return;
    }
    if (EMAIL_TEST_PATTERN.test(token)) {
      creatorBids.push(token.toLowerCase());
      return;
    }
    if (CREATOR_ID_PATTERN.test(token)) {
      creatorBids.push(token);
      return;
    }
    invalidItems.push(token);
  };

  normalized.split(/\r?\n/).forEach(rawLine => {
    const line = trimInvalidDisplay(rawLine);
    if (!line) {
      return;
    }
    if (/[;,]/.test(line)) {
      splitIdentifierTokens(line).forEach(addToken);
      return;
    }
    const contactMatches =
      contactMode === 'email'
        ? findEmailIdentifiers(line)
        : findPhoneIdentifiers(line);
    if (contactMatches.length > 0) {
      if (contactMode === 'email') {
        creatorBids.push(...contactMatches);
        return;
      }
      mobiles.push(...contactMatches);
      return;
    }

    splitIdentifierTokens(line).forEach(addToken);
  });

  return {
    creatorBids: Array.from(new Set(creatorBids)),
    invalidItems: Array.from(new Set(invalidItems)),
    mobiles: Array.from(new Set(mobiles)),
  };
};

const mergeIdentifierLists = (...lists: string[][]) =>
  Array.from(
    new Set(
      lists.flatMap(list => list.map(item => item.trim()).filter(Boolean)),
    ),
  );

const buildListDetails = (
  identifiers: string[],
  resolvedItems: AdminOperationCreditNotificationPolicyListItem[] = [],
) => {
  const resolvedByIdentifier = new Map(
    resolvedItems.map(item => [item.identifier, item]),
  );
  return identifiers.map(identifier => ({
    identifier,
    creator_bid: resolvedByIdentifier.get(identifier)?.creator_bid || '',
    mobile: resolvedByIdentifier.get(identifier)?.mobile || '',
    email: resolvedByIdentifier.get(identifier)?.email || '',
    nickname: resolvedByIdentifier.get(identifier)?.nickname || '',
  }));
};

const filterListDetails = (
  items: AdminOperationCreditNotificationPolicyListItem[],
  keyword: string,
  contactMode: 'email' | 'phone',
) => {
  const normalized = keyword.trim().toLowerCase();
  if (!normalized) {
    return items;
  }
  return items.filter(item => {
    const contactValue =
      contactMode === 'email'
        ? item.email || item.identifier
        : item.mobile || item.identifier;
    const isContactSearch =
      contactMode === 'email'
        ? normalized.includes('@')
        : /^\d+$/.test(normalized);
    if (isContactSearch) {
      return contactValue.toLowerCase() === normalized;
    }
    return item.nickname.toLowerCase().includes(normalized);
  });
};

export function useCreditNotificationConfigTabState({
  contactMode,
  policy,
  resolvedLists,
  updatePolicy,
  t,
}: {
  contactMode: 'email' | 'phone';
  policy: AdminOperationCreditNotificationPolicy;
  resolvedLists: AdminOperationCreditNotificationPolicyResolvedLists;
  updatePolicy: UpdatePolicy;
  t: TFunction;
}) {
  const [openTemplatePicker, setOpenTemplatePicker] = useState<
    Partial<Record<KnownNotificationType, boolean>>
  >({});
  const [editingTemplateTypes, setEditingTemplateTypes] = useState<
    Partial<Record<KnownNotificationType, boolean>>
  >({});
  const [templateInputValues, setTemplateInputValues] = useState<
    Partial<Record<KnownNotificationType, string>>
  >({});
  const [listInputValues, setListInputValues] = useState<
    Partial<Record<string, string>>
  >({});
  const [blockedCreatorInput, setBlockedCreatorInput] = useState('');
  const [integerInputValues, setIntegerInputValues] = useState<
    Partial<Record<string, string>>
  >({});
  const [managedListDialog, setManagedListDialog] =
    useState<ManagedListType | null>(null);
  const [managedListSearch, setManagedListSearch] = useState('');

  const blockedCreatorIdentifiers = useMemo(
    () =>
      mergeIdentifierLists(
        policy.blacklist.creator_bids,
        policy.blacklist.mobiles,
      ),
    [policy.blacklist.creator_bids, policy.blacklist.mobiles],
  );
  const optedOutCreatorIdentifiers = useMemo(
    () =>
      mergeIdentifierLists(policy.opt_out.creator_bids, policy.opt_out.mobiles),
    [policy.opt_out.creator_bids, policy.opt_out.mobiles],
  );
  const blockedCreatorDetails = useMemo(
    () =>
      buildListDetails(
        blockedCreatorIdentifiers,
        resolvedLists.blacklist?.items || [],
      ),
    [blockedCreatorIdentifiers, resolvedLists.blacklist?.items],
  );
  const optedOutCreatorDetails = useMemo(
    () =>
      buildListDetails(
        optedOutCreatorIdentifiers,
        resolvedLists.opt_out?.items || [],
      ),
    [optedOutCreatorIdentifiers, resolvedLists.opt_out?.items],
  );

  const getListInputValue = (key: string, value: string[]) =>
    listInputValues[key] ?? formatListInput(value);

  const updateListInput = (
    key: string,
    value: string,
    commit: (normalized: string) => void,
  ) => {
    const inputValue = normalizeListInputCharacters(value);
    setListInputValues(current => ({
      ...current,
      [key]: inputValue,
    }));
    commit(inputValue);
  };

  const finishListInput = (key: string, value: string) => {
    setListInputValues(current => {
      const next = { ...current };
      next[key] = formatListInput(parseListInput(value));
      return next;
    });
  };

  const getIntegerInputValue = (key: string, value: number) =>
    integerInputValues[key] ?? String(value);

  const updateIntegerInput = (
    key: string,
    value: string,
    fallback: number,
    commit: (value: number) => void,
  ) => {
    const normalized = normalizeIntegerInput(value);
    setIntegerInputValues(current => ({
      ...current,
      [key]: normalized,
    }));
    commit(readNumber(normalized, fallback));
  };

  const finishIntegerInput = (key: string, value: number) => {
    setIntegerInputValues(current => {
      const next = { ...current };
      next[key] = String(value);
      return next;
    });
  };

  const openManagedListDialog = (type: ManagedListType) => {
    setManagedListDialog(type);
    setManagedListSearch('');
  };

  const closeManagedListDialog = () => {
    setManagedListDialog(null);
    setManagedListSearch('');
  };

  const removeBlockedCreator = (identifier: string) => {
    updatePolicy(draft => {
      draft.blacklist.creator_bids = draft.blacklist.creator_bids.filter(
        item => item !== identifier,
      );
      draft.blacklist.mobiles = draft.blacklist.mobiles.filter(
        item => item !== identifier,
      );
    });
  };

  const addBlockedCreators = () => {
    const normalized = normalizeListInputCharacters(blockedCreatorInput);
    const { creatorBids, invalidItems, mobiles } = parseBlockedCreatorInput(
      normalized,
      contactMode,
    );
    if (invalidItems.length > 0) {
      const sample = invalidItems.slice(0, INVALID_SAMPLE_LIMIT).join(', ');
      toast({
        title: t(
          'module.operationsCreditNotifications.config.listDialog.invalidBlockedCreators',
          {
            values:
              invalidItems.length > INVALID_SAMPLE_LIMIT
                ? `${sample}...`
                : sample,
          },
        ),
        variant: 'destructive',
      });
      return;
    }
    if (creatorBids.length === 0 && mobiles.length === 0) {
      if (blockedCreatorInput) {
        setBlockedCreatorInput('');
      }
      return;
    }
    const existingCreatorBids = new Set(policy.blacklist.creator_bids);
    const existingMobiles = new Set(policy.blacklist.mobiles);
    const nextCreatorBids = creatorBids.filter(
      item => !existingCreatorBids.has(item),
    );
    const nextMobiles = mobiles.filter(item => !existingMobiles.has(item));
    const addedCount = nextCreatorBids.length + nextMobiles.length;
    if (addedCount > MAX_BLOCKED_CREATOR_IMPORT_COUNT) {
      toast({
        title: t(
          'module.operationsCreditNotifications.config.listDialog.blockedCreatorLimit',
          { count: MAX_BLOCKED_CREATOR_IMPORT_COUNT },
        ),
        variant: 'destructive',
      });
      return;
    }
    if (addedCount === 0) {
      setBlockedCreatorInput('');
      toast({
        title: t(
          'module.operationsCreditNotifications.config.listDialog.duplicateBlockedCreators',
        ),
      });
      return;
    }
    updatePolicy(draft => {
      draft.blacklist.creator_bids = Array.from(
        new Set([...draft.blacklist.creator_bids, ...nextCreatorBids]),
      );
      draft.blacklist.mobiles = Array.from(
        new Set([...draft.blacklist.mobiles, ...nextMobiles]),
      );
    });
    setBlockedCreatorInput('');
    toast({
      title: t(
        'module.operationsCreditNotifications.config.listDialog.addedBlockedCreators',
        { count: addedCount },
      ),
    });
  };

  const managedListDetails = useMemo(
    () =>
      managedListDialog === 'blocked'
        ? blockedCreatorDetails
        : optedOutCreatorDetails,
    [blockedCreatorDetails, managedListDialog, optedOutCreatorDetails],
  );
  const filteredManagedListDetails = useMemo(
    () => filterListDetails(managedListDetails, managedListSearch, contactMode),
    [contactMode, managedListDetails, managedListSearch],
  );
  const managedListTitle =
    managedListDialog === 'blocked'
      ? t(
          'module.operationsCreditNotifications.config.fields.blockedCreatorList',
        )
      : t(
          'module.operationsCreditNotifications.config.fields.optedOutCreators',
        );
  const managedListCanDelete = managedListDialog === 'blocked';

  return {
    blockedCreatorIdentifiers,
    blockedCreatorInput,
    closeManagedListDialog,
    editingTemplateTypes,
    filteredManagedListDetails,
    finishIntegerInput,
    finishListInput,
    getIntegerInputValue,
    getListInputValue,
    integerInputValues,
    listInputValues,
    managedListCanDelete,
    managedListDialog,
    managedListSearch,
    managedListTitle,
    openManagedListDialog,
    openTemplatePicker,
    optedOutCreatorIdentifiers,
    removeBlockedCreator,
    setBlockedCreatorInput,
    setEditingTemplateTypes,
    setManagedListSearch,
    setOpenTemplatePicker,
    setTemplateInputValues,
    templateInputValues,
    updateIntegerInput,
    updateListInput,
    addBlockedCreators,
  } satisfies {
    blockedCreatorIdentifiers: string[];
    blockedCreatorInput: string;
    closeManagedListDialog: () => void;
    editingTemplateTypes: Partial<Record<KnownNotificationType, boolean>>;
    filteredManagedListDetails: AdminOperationCreditNotificationPolicyListItem[];
    finishIntegerInput: (key: string, value: number) => void;
    finishListInput: (key: string, value: string) => void;
    getIntegerInputValue: (key: string, value: number) => string;
    getListInputValue: (key: string, value: string[]) => string;
    integerInputValues: Partial<Record<string, string>>;
    listInputValues: Partial<Record<string, string>>;
    managedListCanDelete: boolean;
    managedListDialog: ManagedListType | null;
    managedListSearch: string;
    managedListTitle: string;
    openManagedListDialog: (type: ManagedListType) => void;
    openTemplatePicker: Partial<Record<KnownNotificationType, boolean>>;
    optedOutCreatorIdentifiers: string[];
    removeBlockedCreator: (identifier: string) => void;
    setBlockedCreatorInput: Dispatch<SetStateAction<string>>;
    setEditingTemplateTypes: Dispatch<
      SetStateAction<Partial<Record<KnownNotificationType, boolean>>>
    >;
    setManagedListSearch: Dispatch<SetStateAction<string>>;
    setOpenTemplatePicker: Dispatch<
      SetStateAction<Partial<Record<KnownNotificationType, boolean>>>
    >;
    setTemplateInputValues: Dispatch<
      SetStateAction<Partial<Record<KnownNotificationType, string>>>
    >;
    templateInputValues: Partial<Record<KnownNotificationType, string>>;
    updateIntegerInput: (
      key: string,
      value: string,
      fallback: number,
      commit: (value: number) => void,
    ) => void;
    updateListInput: (
      key: string,
      value: string,
      commit: (normalized: string) => void,
    ) => void;
    addBlockedCreators: () => void;
  };
}
