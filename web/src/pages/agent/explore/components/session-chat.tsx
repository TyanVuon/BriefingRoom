import { FileUploadProps } from '@/components/file-upload';
import { NextMessageInput } from '@/components/message-input/next';
import MessageItem from '@/components/next-message-item';
import PdfSheet from '@/components/pdf-drawer';
import { useClickDrawer } from '@/components/pdf-drawer/hooks';
import { MessageType } from '@/constants/chat';
import { useUploadAgentFileWithProgress } from '@/hooks/use-agent-request';
import { useFetchUserInfo } from '@/hooks/use-user-setting-request';
import { IAgentLogResponse } from '@/interfaces/database/agent';
import { IMessage } from '@/interfaces/database/chat';
import { BeginQuery } from '@/pages/agent/interface';
import { ParameterDialog } from '@/pages/agent/share/parameter-dialog';
import { buildMessageUuidWithRole } from '@/utils/chat';
import { useCallback, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useExploreUrlParams } from '../hooks/use-explore-url-params';
import { useSendSessionMessage } from '../hooks/use-send-session-message';
import { useZeroTrustPrivacy } from '../hooks/use-zero-trust-privacy';
import { HardwareAuthGate } from './hardware-auth-gate';
import { VaultUnlockGate } from './vault-unlock-gate';

interface SessionChatProps {
  session?: IAgentLogResponse;
}

export function SessionChat({ session }: SessionChatProps) {
  const { t } = useTranslation();
  const { data: userInfo } = useFetchUserInfo();
  const { sessionId, isNew } = useExploreUrlParams();
  const hasLocalMessageRef = useRef(false);

  const sessionLoading = false;

  const {
    value,
    derivedMessages,
    scrollRef,
    messageContainerRef,
    sendLoading,
    handleInputChange,
    handlePressEnter,
    stopOutputMessage,
    canvasInfo,
    findReferenceByMessageId,
    appendUploadResponseList,
    removeFile,
    parameterDialogVisible,
    handleParametersOk,
    beginInputs,
    shouldShowParameterDialog,
    setDerivedMessages,
  } = useSendSessionMessage();

  const {
    ephemeral,
    canUseAgent,
    hardware,
    vaultLocked,
    needsTotpSetup,
    obsidianLocked,
    vaultBusy,
    vaultError,
    setupBusy,
    setupError,
    qrDataUrl,
    beginTotpSetup,
    unlockVault,
  } = useZeroTrustPrivacy({
    setDerivedMessages,
  });
  const hasActiveSession = Boolean(
    sessionId || isNew || hasLocalMessageRef.current,
  );

  const { visible, hideModal, documentId, selectedChunk, clickDocumentButton } =
    useClickDrawer();

  // File upload
  const { uploadAgentFile, loading: isUploading } =
    useUploadAgentFileWithProgress();

  const handleUploadFile: NonNullable<FileUploadProps['onUpload']> =
    useCallback(
      async (files, options) => {
        const ret = await uploadAgentFile({ files, options });
        appendUploadResponseList(ret.data, files);
      },
      [appendUploadResponseList, uploadAgentFile],
    );

  useEffect(() => {
    shouldShowParameterDialog();
  }, [shouldShowParameterDialog]);

  useEffect(() => {
    hasLocalMessageRef.current = false;
  }, [sessionId, isNew]);

  useEffect(() => {
    if (ephemeral || hasLocalMessageRef.current) {
      return;
    }
    if (sessionId && session?.id === sessionId && session?.message) {
      const messages = session.message;
      setDerivedMessages(messages as IMessage[]);
    }
  }, [ephemeral, session?.id, session?.message, sessionId, setDerivedMessages]);

  useEffect(() => {
    if (!sessionId && !isNew && !hasLocalMessageRef.current && !sendLoading) {
      setDerivedMessages([]);
    }
  }, [sessionId, isNew, sendLoading, setDerivedMessages]);

  const handleSessionPressEnter = useCallback(async () => {
    if (!canUseAgent) {
      return;
    }
    if (value.trim()) {
      hasLocalMessageRef.current = true;
    }
    return handlePressEnter();
  }, [canUseAgent, handlePressEnter, value]);

  return (
    <>
      <section className="relative flex flex-col h-full">
        <HardwareAuthGate
          locked={hardware.locked}
          registered={hardware.registered}
          needsReprovision={hardware.needsReprovision}
          busy={hardware.busy}
          error={hardware.error}
          onRegister={() => void hardware.registerKey()}
          onUnlock={() => void hardware.unlock()}
        />
        <VaultUnlockGate
          locked={!hardware.locked && vaultLocked}
          needsTotpSetup={!hardware.locked && needsTotpSetup}
          obsidianLocked={!hardware.locked && obsidianLocked}
          busy={vaultBusy}
          error={vaultError}
          qrDataUrl={qrDataUrl}
          setupBusy={setupBusy}
          setupError={setupError}
          onBeginSetup={beginTotpSetup}
          onUnlock={unlockVault}
        />
        {!hasActiveSession && (
          <div className="flex-1 flex items-center justify-center text-text-secondary">
            {t('explore.noSessionSelected')}
          </div>
        )}

        {hasActiveSession && (
          <div
            ref={messageContainerRef}
            className="flex-1 overflow-auto min-h-0 p-5"
          >
            {sessionLoading ? (
              <div className="flex items-center justify-center h-full">
                Loading...
              </div>
            ) : derivedMessages.length === 0 ? (
              <div className="flex items-center justify-center h-full text-text-secondary">
                No messages in this session
              </div>
            ) : (
              <div className="w-full pr-5">
                {derivedMessages.map((message, i) => (
                  <MessageItem
                    loading={
                      message.role === MessageType.Assistant &&
                      sendLoading &&
                      derivedMessages.length - 1 === i
                    }
                    key={buildMessageUuidWithRole(message)}
                    item={message}
                    nickname={userInfo.nickname}
                    avatar={userInfo.avatar}
                    avatarDialog={canvasInfo?.avatar || ''}
                    reference={findReferenceByMessageId(message.id)}
                    clickDocumentButton={clickDocumentButton}
                    index={i}
                    showLikeButton={false}
                    sendLoading={sendLoading}
                    showLog={false}
                  />
                ))}
              </div>
            )}
            <div ref={scrollRef} />
          </div>
        )}
        <section className="p-4">
          <NextMessageInput
            value={value}
            sendLoading={sendLoading}
            disabled={false}
            sendDisabled={sendLoading || !canUseAgent}
            isUploading={isUploading}
            onPressEnter={handleSessionPressEnter}
            onInputChange={handleInputChange}
            stopOutputMessage={stopOutputMessage}
            onUpload={handleUploadFile}
            removeFile={removeFile}
            conversationId=""
          />
        </section>
      </section>

      {parameterDialogVisible && beginInputs.length > 0 && (
        <ParameterDialog
          ok={handleParametersOk}
          data={beginInputs.reduce(
            (acc, item) => {
              const { key, ...rest } = item;
              acc[key] = rest;
              return acc;
            },
            {} as Record<string, Omit<BeginQuery, 'key'>>,
          )}
        />
      )}

      {visible && (
        <PdfSheet
          visible={visible}
          hideModal={hideModal}
          documentId={documentId}
          chunk={selectedChunk}
        />
      )}
    </>
  );
}
