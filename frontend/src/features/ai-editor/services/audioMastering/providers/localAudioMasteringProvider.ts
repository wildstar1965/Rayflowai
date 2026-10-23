import { audioStatus, processAudio, operatorAudioSetup } from '../../../runtime/audio';
import type {
  AudioMasteringRequest,
  AudioMasteringResult,
  AudioMasteringStatus,
} from '../types';

type ElectronAudioMasteringApi = {
  status: () => Promise<AudioMasteringStatus>;
  setup: () => Promise<AudioMasteringStatus>;
  process: (payload: AudioMasteringRequest) => Promise<AudioMasteringResult>;
};

const getElectronAudioMasteringApi = (): ElectronAudioMasteringApi => {
  return {
    status: () => audioStatus('audio-mastering'),
    setup: () => operatorAudioSetup('audio-mastering'),
    process: request => processAudio('audio-mastering', request),
  };
};

export const localAudioMasteringProvider = {
  status(): Promise<AudioMasteringStatus> {
    return getElectronAudioMasteringApi().status();
  },
  setup(): Promise<AudioMasteringStatus> {
    return getElectronAudioMasteringApi().setup();
  },
  run(request: AudioMasteringRequest): Promise<AudioMasteringResult> {
    return getElectronAudioMasteringApi().process(request);
  },
};
